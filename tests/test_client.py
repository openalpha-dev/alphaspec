"""Client and CLI against a fake runtime that speaks the /api/agent/v1 contract."""
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from alphaspec import Client, EvaluationFailed, Rejected
from alphaspec.cli import main

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "artifacts" / "01-ema-cross-us-equity.json"
KEY = "eqk_AAAAAAAAAAAA_" + "B" * 32

GATE = {
    "contractVersion": "0.1", "kind": "gate-result", "subject": "artifact/7/experiment/1",
    "passed": True, "computedBy": "PLATFORM",
    "sample": {"inSampleFrom": "2024-10-08", "inSampleTo": "2026-04-08",
               "outOfSampleFrom": "2026-04-08", "outOfSampleTo": "2026-10-08"},
    "checks": [{"code": "GATE_MIN_SHARPE", "metric": "sharpe", "passed": True, "actual": 1.4, "threshold": 0.8, "hint": "x"}],
}


class FakeRuntime(BaseHTTPRequestHandler):
    state: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, code, body=None):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _route(self, method):
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"code": "API_KEY_INVALID", "message": "bad key"})
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        p, s = self.path, self.state
        if method == "GET" and p == "/api/agent/v1/whoami":
            return self._send(200, {"username": "dev", "keyId": "AAAAAAAAAAAA", "contractVersion": "0.1",
                                    "canDo": ["submit"], "cannotDo": ["orders"]})
        if method == "POST" and p == "/api/agent/v1/artifacts":
            if body.get("title") == "server-rejects":
                return self._send(422, {"message": "bad", "issues": [{"code": "AS011", "path": "/x", "message": "m"}]})
            s["submitted"] = body
            return self._send(201, {"artifactId": 7, "warnings": []})
        if method == "POST" and p == "/api/agent/v1/artifacts/7/evaluate":
            s["polls"] = 0
            return self._send(202, {"evaluationId": 1, "status": "QUEUED"})
        if method == "GET" and p == "/api/agent/v1/artifacts/7/gate-result":
            s["polls"] = s.get("polls", 0) + 1
            if s.get("fail"):
                return self._send(409, {"evaluationId": 1, "status": "FAILED", "error": "no bars"})
            return self._send(202, {"status": "RUNNING"}) if s["polls"] < 2 else self._send(200, GATE)
        if method == "POST" and p == "/api/agent/v1/artifacts/7/promote":
            s["promoted_name"] = (body or {}).get("name")
            return self._send(201, {"strategyId": 99, "created": True, "enabled": False, "next": "start it in the UI"})
        if method == "GET" and p == "/api/agent/v1/artifacts":
            return self._send(200, [{"artifactId": 7, "title": "t", "evaluated": True, "passed": True}])
        return self._send(404, {"message": "no route"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


class _LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind 会对地址做 getfqdn 反查，macOS 上能卡几十秒；本地测试用不着
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@pytest.fixture()
def runtime(monkeypatch):
    FakeRuntime.state = {}
    srv = _LocalServer(("127.0.0.1", 0), FakeRuntime)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("ALPHASPEC_BASE_URL", url)
    monkeypatch.setenv("ALPHASPEC_API_KEY", KEY)
    yield url
    srv.shutdown()


def test_whoami_sends_bearer_key(runtime):
    assert Client().whoami()["keyId"] == "AAAAAAAAAAAA"


def test_wrong_key_is_an_error(runtime):
    with pytest.raises(Exception) as e:
        Client(api_key="eqk_wrong").whoami()
    assert e.value.status == 401


def test_local_validation_blocks_bad_document_without_a_request(runtime):
    doc = json.loads(EXAMPLE.read_text())
    doc["dsl"]["entry"]["right"] = 50
    with pytest.raises(Rejected) as e:
        Client().submit(doc)
    assert e.value.issues[0]["code"] == "SCHEMA"
    assert "submitted" not in FakeRuntime.state


def test_server_side_rejection_carries_issues(runtime):
    doc = json.loads(EXAMPLE.read_text())
    doc["title"] = "server-rejects"
    with pytest.raises(Rejected) as e:
        Client().submit(doc)
    assert e.value.status == 422 and e.value.issues[0]["code"] == "AS011"


def test_wait_polls_until_done(runtime):
    c = Client()
    c.evaluate(7)
    assert c.wait(7, interval=0.01)["passed"] is True
    assert FakeRuntime.state["polls"] == 2


def test_wait_raises_on_failed_evaluation(runtime):
    FakeRuntime.state["fail"] = True
    with pytest.raises(EvaluationFailed, match="no bars"):
        Client().wait(7, interval=0.01)


def test_cli_submit_evaluate_promote_end_to_end(runtime, capsys, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    rc = main(["submit", str(EXAMPLE), "--evaluate", "--promote", "--name", "my strat"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "submitted: artifact 7" in out
    assert "gate PASSED" in out
    assert "paper strategy 99 created (disabled)" in out
    assert FakeRuntime.state["promoted_name"] == "my strat"


def test_cli_exit_codes(runtime, capsys, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    FakeRuntime.state["fail"] = True
    assert main(["evaluate", "7", "--wait"]) == 1
    monkeypatch.delenv("ALPHASPEC_API_KEY")
    assert main(["whoami"]) == 2
    assert main(["whoami", "--api-key", "eqk_wrong"]) == 3
