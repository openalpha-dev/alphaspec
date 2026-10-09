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
import time
import urllib.error
import urllib.request
from typing import Any

from .validate import Report, validate

API_PREFIX = "/api/agent/v1"


class AlphaSpecError(Exception):
    """Any non-success response from the runtime."""

    def __init__(self, status: int, body: Any, message: str | None = None):
        self.status = status
        self.body = body
        detail = body.get("message") if isinstance(body, dict) else None
        super().__init__(message or f"HTTP {status}: {detail or body}")


class Rejected(AlphaSpecError):
    """The document failed validation (locally or on the runtime). ``issues`` lists every problem."""

    def __init__(self, status: int, body: Any, issues: list[dict[str, Any]]):
        self.issues = issues
        super().__init__(status, body, f"rejected with {len(issues)} issue(s)")


class EvaluationFailed(AlphaSpecError):
    """The runtime could not finish an evaluation (no data for the symbols, unsupported universe ...)."""


class Client:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0):
        base_url = base_url or os.environ.get("ALPHASPEC_BASE_URL")
        api_key = api_key or os.environ.get("ALPHASPEC_API_KEY")
        if not base_url:
            raise ValueError("base_url is required (or set ALPHASPEC_BASE_URL)")
        if not api_key:
            raise ValueError("api_key is required (or set ALPHASPEC_API_KEY)")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

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

    def promote(self, artifact_id: int, name: str | None = None) -> dict[str, Any]:
        """Turn a gate-passed artifact into a paper-trading strategy (created disabled;
        the user starts it in the runtime's UI)."""
        return self._request("POST", f"/artifacts/{artifact_id}/promote", {"name": name} if name else None)[1]

    # ------------------------------------------------------------------ http

    def _request(self, method: str, path: str, body: Any = None, allow: tuple[int, ...] = ()) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + API_PREFIX + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "alphaspec-python",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
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
