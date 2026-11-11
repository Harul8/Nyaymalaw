"""Plan AN.48, D176 (pieces 48f7-48f8; owner decisions of 11 Nov 2026): NM's reranking done by its own graphics machine, woken when
needed.

On the hosted installation the main server has no graphics card. The reranker - the same model, reading each question and passage
in one reading of the same length - runs on a graphics machine in the owner's own AWS account in India, which sleeps when it is not
used. This adapter is that reranker as the search sees a model: the reranker's own tokenizer, read here from its local files so that
the search cuts its windows exactly as before, and predict, which has each batch the search makes scored there.

Waking (48f8): at an advocate's message NM asks AWS to start the machine (wake_soon), so that it is up by research; a search that
finds it asleep wakes it too and waits for it, up to WAIT_SECONDS (D176 (2): ten minutes). Where it cannot be had - AWS cannot start
it in that time, or starting it is not permitted because this month's budget has stopped it (D176 (1)) - research pauses
(rerank_port.ResearchPaused): the turn stops, keeping everything finished, and Continue takes it up.

Two outgoing destinations, each through this adapter's own gate (reranker_policy), written to the installation's outgoing-data log:
NM's own reranker, which receives the legal questions and law passages for reranking only and keeps nothing; and AWS's requests
that read and start the machine, which carry no client material (D176 (3), the owner's exceptions). The machine is never stopped
from here: it stops itself when quiet.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path

import httpx

from nm.shared.egress_contracts import DataClass, EgressRefused, Sink
from nm.shared.rerank_port import BUDGET_PAUSED, GRAPHICS_UNAVAILABLE, ResearchPaused

log = logging.getLogger(__name__)

#: NM's own reranker on the owner's graphics machine in India (D176 (3)): the legal questions and law passages, for reranking only.
#: The owner's exception that admits it is recorded at the composition root (composition.reranker_policy), as Gmail's is.
RERANKER_PROCESSOR = "nm-own-reranker"
RERANKER_CLASSES = (DataClass.CLIENT_MATTER,)
#: AWS's requests that read and start NM's own machines (D176 (3)): no client material.
MACHINE_CONTROL_PROCESSOR = "aws-machine-control"
MACHINE_CONTROL_CLASSES = (DataClass.OPERATIONAL,)
#: How long research waits for the machine before it pauses (D176 (2)), and how often it looks meanwhile.
WAIT_SECONDS = 600.0
POLL_SECONDS = 5.0
#: How often AWS is asked again while the machine is awaited (a start already asked for is not asked again sooner).
WAKE_EVERY_SECONDS = 30.0
#: Once research has paused, the turn's other searches pause at once for this long rather than each waiting again.
PAUSE_HOLDS_SECONDS = 60.0
#: Each request's own limits: connecting, a look at the service, and one batch scored (a batch of long pairs takes seconds).
CONNECT_SECONDS = 5.0
LOOK_SECONDS = 5.0
SCORE_SECONDS = 180.0
#: The shared secret is a token the setup writes: printable, and not longer than this.
SECRET_MOST = 256


#: What MachineWaker.wake finds.
AWAKE, DENIED, UNAVAILABLE = "awake", "denied", "unavailable"
#: AWS's words for a request its permissions refuse - starting the machine, once this month's budget has stopped it (D176 (1)).
_REFUSED = frozenset({"UnauthorizedOperation", "AccessDenied", "AccessDeniedException"})


class MachineWaker:
    """Starts NM's graphics machine on AWS where it sleeps (D176, 48f8). The main server's own AWS role may read that one machine
    and start it - no key is kept here; it is never stopped from here."""

    def __init__(self, instance_id: str, region: str, gate, *, client=None):
        if not instance_id or not instance_id.startswith("i-"):
            raise ValueError("The graphics machine is named by its AWS instance ID (i-...).")
        self.instance_id, self.region, self.gate = instance_id, region, gate
        self._client = client
        self._lock = threading.Lock()

    def _ec2(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client = boto3.client("ec2", region_name=self.region, config=Config(
                connect_timeout=CONNECT_SECONDS, read_timeout=30, retries={"max_attempts": 2, "mode": "standard"}))
        return self._client

    def _asked(self):
        self.gate.permit(Sink.COMPUTE, MACHINE_CONTROL_PROCESSOR, MACHINE_CONTROL_CLASSES)

    def wake(self) -> str:
        """AWAKE (running or starting), DENIED (starting it is not permitted: this month's budget, D176 (1)) or UNAVAILABLE (AWS
        could not start it now - stopping, short of capacity or not reachable: ask again). One look and, where it sleeps, one start."""
        from botocore.exceptions import BotoCoreError, ClientError
        with self._lock:
            try:
                self._asked()
                found = self._ec2().describe_instances(InstanceIds=[self.instance_id])
                state = found["Reservations"][0]["Instances"][0]["State"]["Name"]
            except ClientError as exc:
                log.warning("The graphics machine's state could not be read: %s", exc.response.get("Error", {}).get("Code"))
                return UNAVAILABLE
            except (BotoCoreError, KeyError, IndexError, TypeError) as exc:
                log.warning("The graphics machine's state could not be read: %s", type(exc).__name__)
                return UNAVAILABLE
            if state in ("running", "pending"):
                return AWAKE
            if state != "stopped":  # stopping: it can be started once it has stopped
                return UNAVAILABLE
            try:
                self._asked()
                self._ec2().start_instances(InstanceIds=[self.instance_id])
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in _REFUSED:
                    return DENIED
                log.warning("The graphics machine could not be started now: %s", code or "unknown")
                return UNAVAILABLE
            except BotoCoreError as exc:
                log.warning("The graphics machine could not be started now: %s", type(exc).__name__)
                return UNAVAILABLE
            log.info("The graphics machine was asked to start.")
            return AWAKE


class RemoteReranker:
    """The reranker on NM's own graphics machine, as the search's model (D176, 48f7): .tokenizer and .predict, as the model in this
    process had them. model and max_length are what the search reads with here (retrieval.RERANK_MODEL, RERANK_TOKENS): the
    machine must say it reads with the same, or it is not used - a different reranker, or a shorter reading, is the owner's word
    alone (P30)."""

    def __init__(self, url: str, secret_file: Path, gate, tokenizer_folder: Path, *, model: str, max_length: int, waker=None,
                 wait_seconds: float = WAIT_SECONDS, poll_seconds: float = POLL_SECONDS, transport=None,
                 clock=time.monotonic, sleep=time.sleep):
        if not url.startswith(("http://", "https://")):
            raise ValueError("The reranker's address must start with http:// or https://.")
        if not Path(secret_file).is_absolute():
            raise ValueError("The reranker's secret file must be named by its absolute path.")
        self.url, self.secret_file, self.gate = url.rstrip("/"), Path(secret_file), gate
        self.tokenizer_folder, self.model, self.max_length = Path(tokenizer_folder), model, max_length
        self.waker, self.wait_seconds, self.poll_seconds = waker, wait_seconds, poll_seconds
        self.clock, self.sleep = clock, sleep
        self._http = httpx.Client(timeout=httpx.Timeout(SCORE_SECONDS, connect=CONNECT_SECONDS), trust_env=False,
                                  follow_redirects=False, transport=transport)
        self._tokenizer, self._lock = None, threading.Lock()
        self._verified = False
        self._paused = None  # (code, detail, until)

    @property
    def tokenizer(self):
        """The reranker's own tokenizer, from its local files (no weights are needed here), as the model reads with it."""
        with self._lock:
            if self._tokenizer is None:
                from transformers import AutoTokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(str(self.tokenizer_folder), local_files_only=True,
                                                                model_max_length=self.max_length)
            return self._tokenizer

    def wake_soon(self) -> None:
        """At an advocate's message (D176, 48f8): the machine is asked to start now, so that it is up by research. Never waits and
        never fails the message: research's own wait decides."""
        if self.waker is None:
            return

        def wake():
            try:
                self.waker.wake()
            except EgressRefused as exc:
                log.error("Waking the graphics machine is refused by this installation's outgoing-data policy: %s", exc)
        threading.Thread(target=wake, name="graphics-wake", daemon=True).start()

    def predict(self, pairs, batch_size=None, show_progress_bar=False, **_):
        """The scores of one batch of (question window, passage window) pairs, in their order, from the machine's model."""
        batch = [[str(question), str(passage)] for question, passage in pairs]
        if not batch:
            return []
        paused = self._paused
        if paused is not None and self.clock() < paused[2]:
            raise ResearchPaused(paused[0], paused[1])
        body = json.dumps({"pairs": batch}, ensure_ascii=False).encode("utf-8")
        try:
            self.gate.permit(Sink.INDEX, RERANKER_PROCESSOR, RERANKER_CLASSES, size_bytes=len(body))
        except EgressRefused as exc:
            log.error("The reranker is refused by this installation's outgoing-data policy: %s", exc)
            raise self._pause(GRAPHICS_UNAVAILABLE, "refused by the outgoing-data policy") from exc
        scores = self._scored(body)
        if (not isinstance(scores, list) or len(scores) != len(batch)
                or not all(isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score)
                           for score in scores)):
            raise ValueError("The reranker's scores do not match the pairs sent")
        return [float(score) for score in scores]

    def _pause(self, code, detail):
        self._paused = (code, detail, self.clock() + PAUSE_HOLDS_SECONDS)
        log.warning("Research paused: %s (%s)", code, detail)
        return ResearchPaused(code, detail)

    def _secret(self):
        try:
            text = self.secret_file.read_text(encoding="utf-8-sig").strip()
        except OSError as exc:
            log.error("The reranker's secret file cannot be read: %s", type(exc).__name__)
            raise self._pause(GRAPHICS_UNAVAILABLE, "secret file unreadable") from None
        if not text or len(text) > SECRET_MOST or not text.isascii() or not text.isprintable() or " " in text:
            log.error("The reranker's secret file does not hold a usable secret.")
            raise self._pause(GRAPHICS_UNAVAILABLE, "secret unusable")
        return text

    def _scored(self, body):
        deadline, retried = None, False
        while True:
            if not self._verified:
                deadline = self._ready(deadline)
            try:
                response = self._http.post(f"{self.url}/score", content=body, headers={
                    "Authorization": f"Bearer {self._secret()}", "Content-Type": "application/json"})
            except httpx.TransportError:
                # Asleep, still waking, or gone part-way (the budget's stop): woken and waited for, then sent again - until the
                # deadline, after which research pauses.
                self._verified = False
                deadline = deadline or self.clock() + self.wait_seconds
                if self.clock() >= deadline:
                    raise self._pause(GRAPHICS_UNAVAILABLE, "the reranker stopped answering") from None
                self.sleep(self.poll_seconds)
                continue
            if response.status_code == 200:
                try:
                    return response.json()["scores"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError("The reranker's answer could not be read") from exc
            if response.status_code in (401, 403):
                log.error("The reranker refused NM's secret: the two machines' secret files differ.")
                raise self._pause(GRAPHICS_UNAVAILABLE, "secret refused")
            if response.status_code >= 500 and not retried:
                retried = True
                self.sleep(min(self.poll_seconds, 2.0))
                continue
            if response.status_code >= 500:
                raise self._pause(GRAPHICS_UNAVAILABLE, f"the reranker failed ({response.status_code})")
            raise ValueError(f"The reranker refused the batch ({response.status_code})")

    def _ready(self, deadline):
        """Until the machine's service answers and says it reads as the search does: woken where it sleeps, waited for until the
        deadline (WAIT_SECONDS from the first try), then research pauses. Returns the deadline."""
        asked_at = None
        while True:
            look = self._look()
            if look == "ready":
                self._verified = True
                return deadline
            if look == "other model":
                raise self._pause(GRAPHICS_UNAVAILABLE, "the machine reads with another model or length")
            deadline = deadline or self.clock() + self.wait_seconds
            if self.waker is not None and (asked_at is None or self.clock() - asked_at >= WAKE_EVERY_SECONDS):
                asked_at = self.clock()
                try:
                    found = self.waker.wake()
                except EgressRefused as exc:
                    log.error("Waking the graphics machine is refused by this installation's outgoing-data policy: %s", exc)
                    raise self._pause(GRAPHICS_UNAVAILABLE, "waking refused by the outgoing-data policy") from exc
                if found == DENIED:
                    raise self._pause(BUDGET_PAUSED, "starting the graphics machine is not permitted")
            if self.clock() >= deadline:
                raise self._pause(GRAPHICS_UNAVAILABLE, f"not answering after {self.wait_seconds:.0f} s")
            self.sleep(self.poll_seconds)

    def _look(self):
        """'ready', 'other model', or 'asleep' (not answering)."""
        try:
            response = self._http.get(f"{self.url}/health", timeout=LOOK_SECONDS)
            said = response.json() if response.status_code == 200 else None
        except (httpx.TransportError, ValueError):
            return "asleep"
        if not isinstance(said, dict) or said.get("ok") is not True:
            return "asleep"
        if said.get("model") != self.model or said.get("max_length") != self.max_length:
            log.error("The graphics machine reads with %s at %s tokens; NM's search reads with %s at %s.",
                      said.get("model"), said.get("max_length"), self.model, self.max_length)
            return "other model"
        return "ready"
