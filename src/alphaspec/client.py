"""Client for an AlphaSpec runtime's agent API (/api/agent/v1).

Standard library only. Configure with arguments or environment variables:

    ALPHASPEC_BASE_URL   e.g. https://your-runtime.example.com
    ALPHASPEC_API_KEY    eqk_... (created in the runtime's account page)

The API key can submit documents, run evaluations and read results. It cannot place
orders or touch accounts; that boundary is enforced by the runtime, not by this client.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from .validate import Report, validate


def _ssl_context() -> ssl.SSLContext:
    """The system trust store, or certifi's bundle when the system store is empty.

    Python from the python.org macOS installer ships without CA certificates, so every HTTPS call fails
    with CERTIFICATE_VERIFY_FAILED until the user runs "Install Certificates.command". A system store that
    loaded any certificate is kept as is (corporate CAs live there); SSL_CERT_FILE / SSL_CERT_DIR still win.
    """
    ctx = ssl.create_default_context()
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return ctx
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        try:
            import certifi
            ctx.load_verify_locations(cafile=certifi.where())
        except ImportError:
            pass
    return ctx
from ._resources import default_lang

API_PREFIX = "/api/agent/v1"


class AlphaSpecError(Exception):
    """Any non-success response from the runtime."""

    def __init__(self, status: int, body: Any, message: str | None = None):
        self.status = status
        self.body = body
        detail = body.get("message") if isinstance(body, dict) else None
        if isinstance(body, dict) and detail:
            # Machine-readable code and the runtime's advice (who can fix it) travel with the message,
            # so the CLI and MCP tools show them without special-casing each error.
            if body.get("code"):
                detail = f"{body['code']}: {detail}"
            if body.get("hint"):
                detail = f"{detail} (hint: {body['hint']})"
        super().__init__(message or f"HTTP {status}: {detail or body}")

    @property
    def code(self) -> str | None:
        """The runtime's error code when it sent one (e.g. ``ACCOUNT_REQUIRED``)."""
        return self.body.get("code") if isinstance(self.body, dict) else None


class Rejected(AlphaSpecError):
    """The document failed validation (locally or on the runtime). ``issues`` lists every problem."""

    def __init__(self, status: int, body: Any, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__(status, body, f"rejected with {len(issues)} issue(s)")


class EvaluationFailed(AlphaSpecError):
    """The runtime could not finish an evaluation (no data for the symbols, unsupported universe ...)."""


class Client:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0,
                 lang: str | None = None):
        base_url = base_url or os.environ.get("ALPHASPEC_BASE_URL")
        api_key = api_key or os.environ.get("ALPHASPEC_API_KEY")
        if not base_url:
            raise ValueError("base_url is required (or set ALPHASPEC_BASE_URL)")
        if not api_key:
            raise ValueError("api_key is required (or set ALPHASPEC_API_KEY)")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        # Language of human-readable text in responses (messages, hints, reasons). Codes, paths and metric
        # keys never change with it -- branch on those. Default: $ALPHASPEC_LANG, else from the locale.
        if lang is not None and lang not in ("en", "zh"):
            raise ValueError("lang must be 'en' or 'zh'")
        self.lang = lang or default_lang()

    # ------------------------------------------------------------------ calls

    def whoami(self) -> dict[str, Any]:
        return self._request("GET", "/whoami")[1]

    def submit(self, doc: dict[str, Any], validate_locally: bool = True) -> dict[str, Any]:
        """Submit an artifact. Returns ``{"artifactId": ..., "warnings": [...]}``.

        Validates locally first (same rules as the runtime) so obvious mistakes never
        cost a round trip. Raises :class:`Rejected` with every issue on failure.
        """
        if validate_locally:
            report: Report = validate(doc)
            if not report.ok:
                raise Rejected(0, None, [i.__dict__ for i in report.issues])
        return self._request("POST", "/artifacts", doc)[1]

    def list(self) -> list[dict[str, Any]]:
        return self._request("GET", "/artifacts")[1]

    def evaluate(self, artifact_id: int) -> dict[str, Any]:
        """Start a platform evaluation. Returns ``{"evaluationId", "status"}`` immediately."""
        return self._request("POST", f"/artifacts/{artifact_id}/evaluate")[1]

    def gate_result(self, artifact_id: int) -> tuple[str, dict[str, Any]]:
        """Return ``(state, body)`` where state is DONE, RUNNING or FAILED.

        DONE carries the gate-result document; RUNNING and FAILED carry ``{"status", "error"?}``.
        """
        status, body = self._request("GET", f"/artifacts/{artifact_id}/gate-result", allow=(202, 409))
        if status == 202:
            return "RUNNING", body
        if status == 409:
            return "FAILED", body
        return "DONE", body

    def wait(self, artifact_id: int, timeout: float = 900, interval: float = 3) -> dict[str, Any]:
        """Poll until the evaluation finishes. Returns the gate-result document."""
        deadline = time.monotonic() + timeout
        while True:
            state, body = self.gate_result(artifact_id)
            if state == "DONE":
                return body
            if state == "FAILED":
                raise EvaluationFailed(409, body, f"evaluation failed: {body.get('error')}")
            if time.monotonic() > deadline:
                raise TimeoutError(f"evaluation of artifact {artifact_id} still running after {timeout}s")
            time.sleep(interval)

    def promote(self, artifact_id: int, name: str | None = None,
                target_strategy_id: int | None = None) -> dict[str, Any]:
        """Turn a gate-passed artifact into a paper-trading strategy (created disabled;
        the user starts it in the runtime's UI).

        With ``target_strategy_id`` the artifact is published as a new version of that existing
        strategy instead (same market and universe required), e.g. after :meth:`export_strategy`.
        """
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if target_strategy_id is not None:
            body["targetStrategyId"] = target_strategy_id
        return self._request("POST", f"/artifacts/{artifact_id}/promote", body or None)[1]

    def factors(self) -> dict[str, Any]:
        """Factors you can bind (``{"factors": [...], "scores": [...]}``). Use a factor's ``factor`` value, or
        ``score:<scoreName>`` for a score series you uploaded, in ``factorBindings[].factor``."""
        return self._request("GET", "/factors")[1]

    def submit_scores(self, docs: dict[str, Any] | list[dict[str, Any]], validate_locally: bool = True) -> dict[str, Any]:
        """Upload score documents (one or a list, same scoreName and market). Re-uploading a date replaces it.
        Returns ``{scoreName, market, factor, dates, rows}``; bind it as ``factor``."""
        batch = docs if isinstance(docs, list) else [docs]
        if validate_locally:
            issues = []
            for i, d in enumerate(batch):
                for issue in validate(d).errors:
                    issues.append({**issue.__dict__, "path": f"/{i}{issue.path}"})
            if issues:
                raise Rejected(0, None, issues)
        # Writing years of scores takes the runtime longer than an ordinary call.
        return self._request("POST", "/scores", batch, timeout=max(self.timeout, 300))[1]

    def scores(self) -> list[dict[str, Any]]:
        """Your uploaded score series with their date coverage."""
        return self._request("GET", "/scores")[1]

    def evidence(self, strategy_id: int | None = None, artifact_id: int | None = None,
                 date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
        """What actually happened when a strategy ran: rejections, execution quality, risk hits, fills and
        whether it ran when it should have (an ``evidence`` document). Pass ``strategy_id``, or ``artifact_id``
        for the strategy an artifact was promoted to. Dates are the market's local dates; default last 30 days."""
        if (strategy_id is None) == (artifact_id is None):
            raise ValueError("pass exactly one of strategy_id or artifact_id")
        path = f"/strategies/{strategy_id}/evidence" if strategy_id is not None else f"/artifacts/{artifact_id}/evidence"
        query = "&".join(f"{k}={v}" for k, v in (("from", date_from), ("to", date_to)) if v)
        return self._request("GET", path + (f"?{query}" if query else ""))[1]

    def capabilities(self) -> dict[str, Any]:
        """What the runtime can evaluate right now: markets with enough history, indicator
        profiles, whether a market can be promoted, benchmarks, windows and today's quota.
        Read it before writing a document."""
        return self._request("GET", "/capabilities")[1]

    def strategies(self) -> list[dict[str, Any]]:
        """Your existing strategies on the runtime (the ones :meth:`export_strategy` can export)."""
        return self._request("GET", "/strategies")[1]

    def export_strategy(self, strategy_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Export an existing strategy as an AlphaSpec artifact. Returns ``(document, issues)``.

        When ``issues`` contains errors the document does not validate as exported (for example a
        factor strategy, which AlphaSpec cannot express before 0.4); it is returned anyway so you
        can see how far it got.
        """
        _, body = self._request("GET", f"/strategies/{strategy_id}/alphaspec", allow=(422,))
        return body.get("document"), body.get("issues", [])

    # ------------------------------------------------------------------ http

    def _request(self, method: str, path: str, body: Any = None, allow: tuple[int, ...] = (),
                 timeout: float | None = None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + API_PREFIX + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "en" if self.lang == "en" else "zh-CN",
                "User-Agent": "alphaspec-python",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout, context=_ssl_context()) as resp:
                return resp.status, _decode(resp.read())
        except urllib.error.HTTPError as e:
            payload = _decode(e.read())
            if e.code in allow:
                return e.code, payload
            if e.code == 422 and isinstance(payload, dict):
                raise Rejected(422, payload, payload.get("issues", [])) from None
            raise AlphaSpecError(e.code, payload) from None


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")
