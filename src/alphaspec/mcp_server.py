"""MCP server (stdio) for agents that cannot run a shell.

    pip install "alphaspec[mcp]"
    alphaspec-mcp                      # started by the MCP client, not by hand

The harness talks MCP (JSON-RPC over stdio) to this process; this process talks HTTPS to the
runtime's /api/agent/v1 with the same :class:`Client` the CLI uses. Nothing here adds a
capability the public API does not already have, and no tool can place orders.

Offline tools (validate, catalog, schema, examples, docs) work without any configuration.
Runtime tools read ALPHASPEC_BASE_URL and ALPHASPEC_API_KEY from the environment the client
passes to this process.
"""
from __future__ import annotations

import json
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]

from . import __version__
from ._resources import data_root, default_lang, load_catalog, load_schema, localized
from .cli import _DOCS, _market_allows
from .client import AlphaSpecError, Client, Rejected
from .lints import RULES
from .validate import validate as _validate

INSTRUCTIONS = """AlphaSpec documents are JSON trading-strategy contracts with no code in them.
Never invent indicator names or parameter keys: find them with search_indicators / get_indicator
and read each entry's pitfalls. Start from get_example, then call validate until there are no
errors. Constants are {"const": n}, never bare numbers. Set producer.searchTrials to every
candidate you evaluated, discarded ones included. Submit only when the user wants the strategy
run; evaluations have a daily quota, so do not loop submissions hunting for a passing variant.
Never state performance numbers the runtime did not return. promote creates a DISABLED paper
strategy; tell the user to start it themselves. No tool here can place orders."""

server = MCPServer("alphaspec", instructions=INSTRUCTIONS, version=__version__)


def _client() -> Client:
    try:
        return Client()
    except ValueError as exc:
        raise ToolError(f"{exc}. Set it in this MCP server's env block in the client config.") from None


def _call(fn, *args):
    try:
        return fn(*args)
    except Rejected:
        raise
    except AlphaSpecError as exc:
        raise ToolError(str(exc)) from None
    except OSError as exc:
        raise ToolError(f"cannot reach runtime: {exc}") from None


def _report(doc: Any) -> dict[str, Any]:
    r = _validate(doc)
    return {"ok": r.ok, "kind": r.kind, "errors": len(r.errors), "warnings": len(r.warnings),
            "issues": [i.__dict__ for i in r.issues]}


def _lang(lang: str) -> str:
    if lang and lang not in ("en", "zh"):
        raise ToolError("lang must be en or zh")
    return lang or default_lang()


def _as_doc(document: dict[str, Any] | str) -> Any:
    # Some clients pass nested objects as a JSON string.
    if isinstance(document, str):
        try:
            return json.loads(document)
        except json.JSONDecodeError as exc:
            raise ToolError(f"document is not valid JSON: {exc}") from None
    return document


# ---------------------------------------------------------------- offline

@server.tool()
def validate(document: dict[str, Any] | str) -> dict[str, Any]:
    """Validate an AlphaSpec document (artifact or score) locally, with the same rules the runtime
    applies. Fix every error; treat warnings as probable mistakes. Use explain_rule for any code."""
    return _report(_as_doc(document))


@server.tool()
def explain_rule(code: str) -> str:
    """Why a lint rule (e.g. AS003) exists and how to fix a document that breaks it."""
    code = code.upper()
    text = (data_root() / "docs" / "RULES.md").read_text(encoding="utf-8")
    start = text.find(f"### {code}")
    if start < 0:
        raise ToolError(f"unknown rule {code}; known: {', '.join(RULES)}")
    end = text.find("\n### ", start + 1)
    return text[start:end if end > 0 else None].strip()


@server.tool()
def search_indicators(query: str = "", market: str = "", profile: str = "", lang: str = "") -> list[dict[str, Any]]:
    """Find indicator types you may use. query matches name, summary and parameters in English or
    Chinese (e.g. "RSI", "moving average", "breakout", "均线"); market hides types unavailable there
    (e.g. us_equity hides China-only ones); profile is core | ext.cn | ext.l2 | ext.data; lang is en | zh.
    Returns a compact list; call get_indicator for parameters, units and pitfalls before using a type."""
    lang = _lang(lang)
    q = query.lower()
    rows = []
    for t in load_catalog()["types"]:
        if profile and t["profile"] != profile:
            continue
        if not _market_allows(t["profile"], market or None):
            continue
        if q and q not in json.dumps(t, ensure_ascii=False).lower():
            continue
        loc = localized(t, lang)
        rows.append({"type": t["type"], "profile": t["profile"], "label": loc.get("label", ""),
                     "summary": loc.get("summary", ""),
                     "params": [p["key"] for p in t.get("params", [])],
                     "operands": t.get("operandKeys", [])})
    return rows


@server.tool()
def get_indicator(type: str, lang: str = "") -> dict[str, Any]:
    """Full catalog entry for one indicator type: parameter keys, defaults, ranges, unit, pitfalls.
    lang is en | zh."""
    t = next((x for x in load_catalog()["types"] if x["type"] == type.upper()), None)
    if t is None:
        raise ToolError(f"unknown indicator type {type}; use search_indicators")
    return localized(t, _lang(lang))


@server.tool()
def get_schema(kind: str) -> dict[str, Any]:
    """JSON Schema for a document kind: artifact, score, gate-result, evidence or common."""
    if kind not in ("artifact", "score", "gate-result", "evidence", "common"):
        raise ToolError("kind must be one of artifact, score, gate-result, evidence, common")
    return load_schema(kind)


@server.tool()
def list_examples() -> list[dict[str, Any]]:
    """Example documents to start from."""
    out = []
    for f in sorted((data_root() / "examples").rglob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        out.append({"name": f.stem, "kind": doc.get("kind"), "market": doc.get("market"),
                    "title": doc.get("title") or doc.get("scoreName")})
    return out


@server.tool()
def get_example(name: str) -> dict[str, Any]:
    """One example document by name (a prefix such as "01-ema-cross" is enough)."""
    match = [f for f in sorted((data_root() / "examples").rglob("*.json"))
             if f.stem == name or f.stem.startswith(name)]
    if not match:
        raise ToolError(f"no example named {name}; use list_examples")
    return json.loads(match[0].read_text(encoding="utf-8"))


@server.tool()
def get_doc(name: str) -> str:
    """Reference document: spec (field semantics), rules (every lint rule), markets, runtime (API and gate)."""
    if name not in _DOCS:
        raise ToolError(f"name must be one of {', '.join(sorted(_DOCS))}")
    return (data_root() / "docs" / _DOCS[name]).read_text(encoding="utf-8")


# ---------------------------------------------------------------- runtime

@server.tool()
def whoami() -> dict[str, Any]:
    """Check the configured API key: user, contract version, what the key can and cannot do."""
    return _call(_client().whoami)


@server.tool()
def submit(document: dict[str, Any] | str) -> dict[str, Any]:
    """Validate locally, then submit an artifact to the runtime. Returns {accepted, artifactId,
    warnings} or {accepted: false, issues}. Submitting does not run anything; call evaluate."""
    doc = _as_doc(document)
    try:
        res = _call(_client().submit, doc)
    except Rejected as exc:  # subclass of AlphaSpecError, but a normal outcome for an agent
        return {"accepted": False, "issues": exc.issues}
    return {"accepted": True, **res}


@server.tool()
def evaluate(artifact_id: int) -> dict[str, Any]:
    """Start a platform evaluation (one backtest, in-sample and out-of-sample segments chosen by the
    runtime). Returns immediately; poll gate_result every few seconds. Uses the daily quota."""
    return _call(_client().evaluate, artifact_id)


@server.tool()
def gate_result(artifact_id: int) -> dict[str, Any]:
    """Latest evaluation of an artifact. state is RUNNING (poll again later), FAILED (error says why)
    or DONE (result is the gate-result document). Each check names its number in `metric`; read it
    instead of guessing from the code."""
    state, body = _call(_client().gate_result, artifact_id)
    return {"state": state, "result" if state == "DONE" else "detail": body}


@server.tool()
def list_submissions() -> list[dict[str, Any]]:
    """My submitted artifacts, newest first, with the latest verdict."""
    return _call(_client().list)


@server.tool()
def promote(artifact_id: int, name: str = "") -> dict[str, Any]:
    """Turn a gate-passed artifact into a paper-trading strategy. It is created DISABLED; the user
    starts it in the runtime's UI. Only call this when the user asked for it."""
    return _call(_client().promote, artifact_id, name or None)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
