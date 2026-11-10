"""A stalled AI request is noticed and sent again within minutes (plan AN.48, owner decision D174, 10 Nov 2026).

Two requests of the pilot's browser test stalled for the AI client's default 600 s each before they were tried again. Each Responses
request now carries a time limit by the effort it reasons at, and the HTTP client NM builds sends TCP keep-alive probes on its
connections, so that a dead connection fails within about a minute. Offline: the AI client's own request path over a mock transport,
and one real connection to a server on this machine - never the provider."""
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx2
import pytest
from openai import OpenAI

from nm.shared.model_config import ModelConfig, TierConfig
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import Prompt, Tier

pytestmark = pytest.mark.class_a

MODEL = "gpt-6-luna"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"],
          "properties": {"answer": {"type": "string"}}}


def answered():
    return httpx2.Response(200, json={
        "id": "synthetic-response", "object": "response", "created_at": 0, "model": MODEL, "status": "completed",
        "error": None, "incomplete_details": None,
        "usage": {"input_tokens": 100, "output_tokens": 10,
                  "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}},
        "output": [{"type": "message", "id": "synthetic-message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": '{"answer":"supported"}', "annotations": []}]}]})


def adapter_over(handler):
    client = OpenAI(api_key="synthetic-no-network", base_url="http://fixture.invalid/v1", max_retries=0,
                    http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL, "unused", None)})
    return OpenAIModelAdapter(config, client=client), client


def ask(adapter, effort):
    return adapter.structured(Prompt(user='{"latest":"Synthetic words"}', effort=effort), SCHEMA, Tier.ROUTINE, max_tokens=200)


@pytest.mark.parametrize("effort, seconds", [(None, 180.0), ("low", 180.0), ("medium", 180.0), ("high", 420.0), ("max", 1200.0)])
def test_each_request_carries_the_time_limit_of_the_effort_it_reasons_at(effort, seconds):
    """About two and a half times the slowest such call measured (medium 71 s, high 184 s on 6 Luna); max, not measured, twenty
    minutes; a call at the release's own setting (None) reasons at low. Connecting is given 10 s."""
    seen = []

    def handler(request):
        seen.append(dict(request.extensions["timeout"]))
        return answered()
    adapter, client = adapter_over(handler)
    try:
        result = ask(adapter, effort)
    finally:
        client.close()
    assert seen == [{"connect": 10.0, "read": seconds, "write": seconds, "pool": seconds}]
    assert result.retries == 0


def test_a_request_given_up_at_its_limit_is_sent_again_and_answered():
    """The stall the test met, now cut at the limit: the first attempt gets no answer in time, the second is answered."""
    attempts = []

    def handler(request):
        attempts.append(request.extensions["timeout"]["read"])
        if len(attempts) == 1:
            raise httpx2.ReadTimeout("synthetic: no answer within the limit", request=request)
        return answered()
    adapter, client = adapter_over(handler)
    try:
        result = ask(adapter, "medium")
    finally:
        client.close()
    assert attempts == [180.0, 180.0] and result.retries == 1


def test_a_request_that_never_answers_is_given_up_after_three_attempts_not_waited_on():
    attempts = []

    def handler(request):
        attempts.append(1)
        raise httpx2.ReadTimeout("synthetic: no answer within the limit", request=request)
    adapter, client = adapter_over(handler)
    try:
        with pytest.raises(Exception) as raised:
            ask(adapter, "high")
    finally:
        client.close()
    assert len(attempts) == 3, "the existing retry's bound: three attempts, then the step says the service is unavailable"
    assert "Timeout" in type(raised.value).__name__ or "Unavailable" in type(raised.value).__name__, type(raised.value)


class _Answers(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keeps the connection open after answering, as the AI service's does

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def test_the_client_nm_builds_sends_keep_alive_probes_on_a_real_connection():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Answers)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    config = ModelConfig({Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", MODEL, "synthetic-key", base + "/v1")})
    adapter = OpenAIModelAdapter(config)
    http = adapter._client._client  # the HTTP client NM built for the AI client
    try:
        # What it refused before it still refuses: redirects, and proxies taken from the machine's settings.
        assert http.follow_redirects is False and http.trust_env is False
        assert http.get(base + "/probe").status_code == 200
        (connection,) = http._transport._pool.connections
        sock = connection._connection._network_stream.get_extra_info("socket")
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
        for name, value in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
            if hasattr(socket, name):
                assert sock.getsockopt(socket.IPPROTO_TCP, getattr(socket, name)) == value, name
    finally:
        http.close()
        server.shutdown()
        server.server_close()
