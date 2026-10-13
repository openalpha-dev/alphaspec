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


CAPS = {
    "contractVersion": "0.3", "kind": "capabilities", "contractVersions": ["0.1", "0.2", "0.3"],
    "evaluation": {
        "daily": {"timeframes": ["1d", "1w"], "inSampleMonths": 48, "outOfSampleMonths": 12,
                  "inSampleFrom": "2021-10-12", "outOfSampleFrom": "2025-10-12", "to": "2026-10-12"},
        "intraday": {"timeframes": ["5m"], "inSampleMonths": 18, "outOfSampleMonths": 6},
        "universeModes": ["SYMBOLS", "UNIVERSE"], "sizingModes": ["FIXED_PCT", "ATR_RISK"],
        "quota": {"limit": 10, "used": 2, "remaining": 8, "resetsAt": "2026-10-12T16:00:00Z"},
    },
    "markets": [
        {"id": "cn_stock", "evaluation": {"daily": {"timeframes": ["1d"], "evaluable": True},
                                          "intraday": {"timeframes": ["5m"], "evaluable": False, "reason": "no 1m bars"}},
         "indicatorProfiles": ["core", "ext.cn"], "promotable": True, "benchmark": {"code": "000300.SH", "name": "CSI 300"}},
        {"id": "us_equity", "evaluation": {"daily": {"timeframes": ["1d"], "evaluable": False, "reason": "daily bars from 2026-04-02"}},
         "indicatorProfiles": ["core"], "promotable": False, "benchmark": None},
    ],
}

EVIDENCE = {
    "contractVersion": "0.4", "kind": "evidence",
    "subject": {"strategy": "strategy/438", "mode": "PAPER"},
    "window": {"from": "2026-09-12", "to": "2026-10-12", "timezone": "Asia/Shanghai"},
    "caliber": {"slippageBasis": "VS_ARRIVAL_PRICE", "feeIncluded": False, "volumeUnit": "SHARE", "currency": "CNY"},
    "rejects": [{"category": "RISK", "code": "RISK_ORDER_LIMIT", "count": 3, "message": "daily order limit"}],
    "executionQuality": {"orders": 10, "fillRatePct": 70.0, "rejectRatePct": 30.0, "avgSlippageBps": 4.2, "p95SlippageBps": 11.0},
    "riskHits": [{"code": "RISK_ORDER_LIMIT", "count": 3, "blocking": True}],
    "ledger": [{"ts": "2026-10-09T01:31:00Z", "symbol": "600519.SH", "side": "BUY", "qty": 100, "price": 1500.0}],
    "pipeline": [{"stage": "STRATEGY_ENABLED", "status": "OK"}, {"stage": "SIGNAL_EVALUATION", "status": "OK"}],
}

EXPORTED = json.loads((ROOT / "examples" / "artifacts" / "06-trend-with-trade-settings.json").read_text())


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
        s["accept_language"] = self.headers.get("Accept-Language")
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
        if method == "GET" and p == "/api/agent/v1/capabilities":
            return self._send(200, CAPS)
        if method == "GET" and p == "/api/agent/v1/strategies":
            return self._send(200, [{"strategyId": 438, "name": "MACD", "market": "cn_stock", "timeframe": "1d", "enabled": True}])
        if method == "GET" and p == "/api/agent/v1/strategies/438/alphaspec":
            return self._send(200, {"document": EXPORTED, "issues": []})
        if method == "GET" and p == "/api/agent/v1/strategies/9/alphaspec":
            return self._send(422, {"document": {"kind": "artifact"},
                                    "issues": [{"code": "EXPORT_UNSUPPORTED", "severity": "ERROR", "path": "/signalMode", "message": "factor"}]})
        if method == "POST" and p == "/api/agent/v1/artifacts/8/promote":
            s["promote_body"] = body
            return self._send(200, {"strategyId": 438, "created": False, "updated": True, "next": "new version"})
        if method == "GET" and p == "/api/agent/v1/factors":
            return self._send(200, {"factors": [{"factor": "MOMENTUM", "source": "GLOBAL", "name": "Momentum", "category": "MOMENTUM",
                                                 "locked": False}],
                                    "scores": [{"factor": "score:my-model", "market": "cn_stock", "from": "2023-10-13",
                                                "to": "2026-10-09", "days": 730}]})
        if method == "POST" and p == "/api/agent/v1/scores":
            s["scores_body"] = body
            return self._send(201, {"scoreName": "my-model", "market": "cn_stock", "factor": "score:my-model",
                                    "dates": len(body), "rows": sum(len(d["scores"]) for d in body)})
        if method == "GET" and p.startswith("/api/agent/v1/strategies/438/evidence"):
            s["evidence_path"] = p
            return self._send(200, EVIDENCE)
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


def test_language_goes_out_as_accept_language(runtime, monkeypatch, capsys):
    monkeypatch.setenv("ALPHASPEC_LANG", "en")
    Client().whoami()
    assert FakeRuntime.state["accept_language"] == "en"
    Client(lang="zh").whoami()
    assert FakeRuntime.state["accept_language"] == "zh-CN"
    with pytest.raises(ValueError):
        Client(lang="fr")
    assert main(["whoami", "--lang", "zh"]) == 0
    assert FakeRuntime.state["accept_language"] == "zh-CN"
    capsys.readouterr()


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


def test_capabilities_document_validates_and_prints(runtime, capsys):
    from alphaspec import validate
    cap = Client().capabilities()
    assert validate(cap).ok, validate(cap).issues
    assert main(["capabilities"]) == 0
    out = capsys.readouterr().out
    assert "us_equity" in out and "daily bars from 2026-04-02" in out and "evaluations today 2/10" in out


def test_export_then_promote_as_new_version(runtime, capsys, tmp_path):
    doc, issues = Client().export_strategy(438)
    assert issues == [] and doc["kind"] == "artifact"
    out_file = tmp_path / "s.json"
    assert main(["export", "438", "-o", str(out_file)]) == 0
    assert json.loads(out_file.read_text())["title"] == doc["title"]
    assert main(["promote", "8", "--target", "438"]) == 0
    assert FakeRuntime.state["promote_body"] == {"targetStrategyId": 438}
    assert "new version" in capsys.readouterr().out


def test_export_with_errors_returns_document_and_exit_code_1(runtime, capsys):
    doc, issues = Client().export_strategy(9)
    assert issues[0]["code"] == "EXPORT_UNSUPPORTED"
    assert main(["export", "9"]) == 1
    assert "EXPORT_UNSUPPORTED" in capsys.readouterr().err


def test_factors_scores_and_evidence(runtime, capsys, tmp_path):
    from alphaspec import validate
    c = Client()
    assert c.factors()["factors"][0]["factor"] == "MOMENTUM"
    score = json.loads((ROOT / "examples" / "scores" / "01-model-scores-cn-stock.json").read_text())
    lines = tmp_path / "scores.jsonl"
    lines.write_text("\n".join(json.dumps(dict(score, asOf=d)) for d in ("2026-10-08", "2026-10-09")))
    assert main(["submit-scores", str(lines)]) == 0
    assert len(FakeRuntime.state["scores_body"]) == 2
    assert "score:my-model" in capsys.readouterr().out

    ev = c.evidence(strategy_id=438, date_from="2026-09-12")
    assert validate(ev).ok, validate(ev).issues
    assert FakeRuntime.state["evidence_path"].endswith("from=2026-09-12")
    assert main(["evidence", "438"]) == 0
    out = capsys.readouterr().out
    assert "RISK_ORDER_LIMIT" in out and "VS_ARRIVAL_PRICE" in out


def test_invalid_score_is_rejected_locally(runtime):
    score = json.loads((ROOT / "examples" / "scores" / "01-model-scores-cn-stock.json").read_text())
    score["scores"] = [{"symbol": "600000", "score": 1.0}]
    with pytest.raises(Rejected) as e:
        Client().submit_scores([score])
    assert any(i["code"] == "AS011" for i in e.value.issues)
    assert "scores_body" not in FakeRuntime.state
