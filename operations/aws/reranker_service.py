"""NM's reranker as a small service on the graphics machine (plan AN.48, D176, piece 48f7; owner decisions of 11 Nov 2026).

On the hosted installation the main server has no graphics card; this service, on a graphics machine in the owner's own AWS account
in India, scores the search's batches with the same model NM's search loads on one machine - bge-reranker-v2-m3, each question and
passage read in one reading of up to 8,192 tokens, half precision on the card - and nothing else. The main server sends one batch at
a time, as its search made it (retrieval._batched_scores); the scores come back in the batch's own order.

    python reranker_service.py --models /opt/nm/models --secret-file /etc/nm/reranker.secret --last-use-file /run/nm/last-use

GET /health says it is up and what it reads with; the main server uses NM only where that is what its own search reads with. POST
/score takes {"pairs": [[question, passage], ...]} with the secret both machines share and answers {"scores": [...]}. Nothing it
receives is kept or logged: it logs counts and times only. Each scoring touches the last-use file, by which the machine's idle watch
stops it after 15 quiet minutes (48f10). The machine's firewall admits only the main server.

Standard library only, besides the model: the graphics machine needs torch, sentence-transformers and the weights, no more.
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

#: The same model and reading as NM's search on one machine (nm/core_engine/retrieval.py RERANK_MODEL, RERANK_TOKENS and
#: RERANK_BATCH_PAIRS); a test holds them equal.
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_TOKENS = 8192
RERANK_BATCH_PAIRS = 16
#: One batch is at most 16 pairs and 32,000 characters, or one longer pair alone: a request this size is far beyond any.
MOST_BYTES = 8 * 1024 * 1024
#: The shared secret is a token the setup writes: printable, and not longer than this.
SECRET_MOST = 256

log = logging.getLogger("nm.reranker")


def load_scorer(models: Path):
    """The reranker, loaded as NM's search loads it on one machine (retrieval._Models): its scoring function, the device and the
    precision it reads at."""
    import torch
    from sentence_transformers import CrossEncoder

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CrossEncoder(str(models / RERANK_MODEL.replace("/", "__")), device=device, max_length=RERANK_TOKENS,
                         local_files_only=True, model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {})
    lock = threading.Lock()

    def scores(pairs):
        with lock:  # one batch at a time on the card, as on one machine
            return [float(score) for score in model.predict(pairs, batch_size=len(pairs), show_progress_bar=False)]
    return scores, device, "float16" if device == "cuda" else "float32"


def read_secret(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text or len(text) > SECRET_MOST or not text.isascii() or not text.isprintable() or " " in text:
        raise ValueError("The secret file does not hold a usable secret.")
    return text


def make_server(host, port, scorer, secret_file: Path, *, device, dtype, last_use: Path | None = None,
                model=RERANK_MODEL, max_length=RERANK_TOKENS):
    """The service on host:port (port 0: any free one), scoring with scorer(pairs) -> scores."""
    secret_file = Path(secret_file)
    read_secret(secret_file)  # refuses to start without a usable one

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "nm-reranker"

        def log_message(self, *_):  # the default line names the client and path; counts and times are logged instead
            return

        def _answer(self, status, body, *, close=False):
            """close: the request's body was not read, so the connection is closed - what is left of it must never be read as the
            next request."""
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != "/health":
                return self._answer(404, {"error": "not found"})
            return self._answer(200, {"ok": True, "model": model, "max_length": max_length, "device": device, "dtype": dtype})

        def do_POST(self):
            # The body is read whole before anything is answered (a connection closed on an unread body is reset, and the answer
            # lost with it); only a body of no stated length, or one beyond any batch, is refused unread, closing the connection.
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._answer(411, {"error": "length required"}, close=True)
            if length <= 0 or length > MOST_BYTES:
                return self._answer(413, {"error": "too large"}, close=True)
            body = self.rfile.read(length)
            if self.path != "/score":
                return self._answer(404, {"error": "not found"})
            try:
                expected = read_secret(secret_file)  # read each time: a new secret needs no restart
            except (OSError, ValueError):
                log.error("The secret file cannot be read; every request is refused.")
                return self._answer(503, {"error": "not configured"})
            given = self.headers.get("Authorization", "")
            if not hmac.compare_digest(given.encode("utf-8"), f"Bearer {expected}".encode("utf-8")):
                return self._answer(401, {"error": "not permitted"})
            try:
                pairs = json.loads(body.decode("utf-8"))["pairs"]
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                return self._answer(400, {"error": "unreadable"})
            if (not isinstance(pairs, list) or not 1 <= len(pairs) <= RERANK_BATCH_PAIRS
                    or not all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(text, str) for text in pair)
                               for pair in pairs)):
                return self._answer(400, {"error": "not a batch of pairs"})
            began = time.monotonic()
            try:
                scores = scorer([tuple(pair) for pair in pairs])
            except (RuntimeError, ValueError) as exc:  # the card's own failures (out of memory, say): said, never retried here
                log.error("A batch could not be scored: %s", type(exc).__name__)
                return self._answer(500, {"error": "not scored"})
            if len(scores) != len(pairs) or not all(math.isfinite(score) for score in scores):
                log.error("The model returned scores that do not match the batch.")
                return self._answer(500, {"error": "not scored"})
            if last_use is not None:
                try:
                    last_use.touch()
                except OSError:
                    log.warning("The last-use file could not be touched; the idle watch may stop the machine early.")
            log.info("Scored %d pairs in %.2f s.", len(pairs), time.monotonic() - began)
            return self._answer(200, {"scores": scores})

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", type=Path, required=True, help="the folder that holds BAAI__bge-reranker-v2-m3")
    parser.add_argument("--secret-file", type=Path, required=True)
    parser.add_argument("--last-use-file", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scorer, device, dtype = load_scorer(args.models)
    server = make_server(args.host, args.port, scorer, args.secret_file, device=device, dtype=dtype,
                         last_use=args.last_use_file)
    log.info("The reranker serves on port %d (%s, %s).", server.server_address[1], device, dtype)
    server.serve_forever()


if __name__ == "__main__":
    main()
