"""MCP server end to end: a real MCP client spawns `python -m alphaspec.mcp_server` over stdio,
which talks HTTP to the fake runtime from test_client."""
import asyncio
import json
import os
import sys

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from test_client import EXAMPLE, FakeRuntime, runtime  # noqa: E402,F401


def _run(env: dict[str, str], steps):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "alphaspec.mcp_server"],
                                       env={**os.environ, **env})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await steps(session)
    return asyncio.run(go())


def _payload(result):
    assert not result.is_error if hasattr(result, "is_error") else not result.isError, result.content
    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _error_text(result):
    assert (result.is_error if hasattr(result, "is_error") else result.isError)
    return result.content[0].text


def test_tools_are_listed_and_no_order_tool():
    async def steps(s):
        return [t.name for t in (await s.list_tools()).tools]
    names = _run({}, steps)
    assert {"validate", "search_indicators", "get_indicator", "submit", "evaluate", "gate_result",
            "promote", "list_submissions", "whoami", "get_capabilities", "list_strategies",
            "export_strategy"} <= set(names)
    assert not any("order" in n for n in names)


def test_offline_tools_work_without_configuration():
    doc = json.loads(EXAMPLE.read_text())
    bad = json.loads(EXAMPLE.read_text())
    bad["dsl"]["entry"]["right"] = 50

    async def steps(s):
        return (_payload(await s.call_tool("validate", {"document": doc})),
                _payload(await s.call_tool("validate", {"document": json.dumps(bad)})),
                (await s.call_tool("search_indicators", {"query": "RSI"})).structured_content,
                _payload(await s.call_tool("explain_rule", {"code": "as003"})),
                _error_text(await s.call_tool("whoami", {})))
    ok, broken, rsi, rule, no_key = _run({"ALPHASPEC_BASE_URL": "", "ALPHASPEC_API_KEY": ""}, steps)
    assert ok["ok"] is True
    assert broken["ok"] is False and broken["issues"][0]["code"] == "SCHEMA"
    assert any(r["type"] == "RSI" for r in rsi["result"])
    assert rule.startswith("### AS003")
    assert "ALPHASPEC_BASE_URL" in no_key


def test_submit_evaluate_poll_promote(runtime):
    doc = json.loads(EXAMPLE.read_text())
    rejected = dict(doc, title="server-rejects")

    async def steps(s):
        sub = _payload(await s.call_tool("submit", {"document": doc}))
        rej = _payload(await s.call_tool("submit", {"document": rejected}))
        await s.call_tool("evaluate", {"artifact_id": sub["artifactId"]})
        states = []
        for _ in range(5):
            g = _payload(await s.call_tool("gate_result", {"artifact_id": 7}))
            states.append(g["state"])
            if g["state"] == "DONE":
                break
        promoted = _payload(await s.call_tool("promote", {"artifact_id": 7, "name": "mine"}))
        return sub, rej, states, g, promoted
    sub, rej, states, gate, promoted = _run({"ALPHASPEC_BASE_URL": runtime}, steps)
    assert sub == {"accepted": True, "artifactId": 7, "warnings": []}
    assert rej["accepted"] is False and rej["issues"][0]["code"] == "AS011"
    assert states[0] == "RUNNING" and states[-1] == "DONE"
    assert gate["result"]["checks"][0]["metric"] == "sharpe"
    assert promoted["enabled"] is False and FakeRuntime.state["promoted_name"] == "mine"
