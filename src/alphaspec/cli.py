"""Command line.

    alphaspec validate FILE...              check documents locally (a file may hold one, a JSON array, or JSON lines)
    alphaspec rules [--explain CODE]        list lint rules / why one exists
    alphaspec catalog [--market M] [--profile P] [--search TEXT] [--type T] [--lang en|zh]
                                            indicators you may use, with meaning and parameters
    alphaspec schema KIND                   print a JSON Schema (artifact, score, gate-result, evidence, capabilities, common)
    alphaspec examples [NAME]               list or print example documents
    alphaspec docs NAME                     print a reference document (spec, rules, markets, runtime)
    alphaspec skill [--install DIR]         print the Agent Skill, or write it to DIR/alphaspec/SKILL.md

    alphaspec whoami                        check the API key against the runtime
    alphaspec capabilities                  what the runtime can evaluate now (markets, history, quota)
    alphaspec submit FILE [--evaluate] [--wait] [--promote [--name N]]
    alphaspec evaluate ARTIFACT_ID [--wait]
    alphaspec result ARTIFACT_ID
    alphaspec list
    alphaspec promote ARTIFACT_ID [--name N] [--target STRATEGY_ID]
    alphaspec strategies                    my existing strategies on the runtime
    alphaspec factors [--search TEXT]       factors I can bind, and my uploaded score series
    alphaspec submit-scores FILE...         upload score documents (one per file, or arrays / JSON lines)
    alphaspec scores                        my uploaded score series
    alphaspec evidence (STRATEGY_ID | --artifact ID) [--from D] [--to D]
                                            what happened when it ran
    alphaspec export STRATEGY_ID [-o FILE]  export one as an AlphaSpec artifact to edit and resubmit

Runtime commands read ALPHASPEC_BASE_URL and ALPHASPEC_API_KEY (or --base-url / --api-key).
Exit codes: 0 ok · 1 rejected, gate not passed or evaluation failed · 2 usage · 3 runtime / network error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .client import AlphaSpecError, Client, EvaluationFailed, Rejected
from ._resources import data_root, default_lang, load_catalog, load_schema, localized
from .lints import RULES
from .validate import validate


def _cmd_validate(args: argparse.Namespace) -> int:
    failed = 0
    for name in args.files:
        path = Path(name)
        try:
            docs = _read_docs([name])
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: cannot read: {exc}")
            failed += 1
            continue
        for n, doc in enumerate(docs):
            label = str(path) if len(docs) == 1 else f"{path}#{n}"
            report = validate(doc)
            bad = not report.ok or (args.strict and report.warnings)
            failed += bool(bad)
            if args.json:
                print(json.dumps({
                    "file": label, "kind": report.kind, "ok": not bad,
                    "issues": [i.__dict__ for i in report.issues],
                }, ensure_ascii=False))
                continue
            if len(docs) > 1 and not report.issues:
                continue  # one line per clean document would bury the ones that matter
            status = "FAIL" if bad else "ok"
            print(f"{label}: {status} ({len(report.errors)} errors, {len(report.warnings)} warnings)")
            for issue in report.issues:
                print(f"  {issue}")
        if len(docs) > 1 and not args.json:
            print(f"{path}: {len(docs)} documents checked")
    return 1 if failed else 0


def _cmd_rules(args: argparse.Namespace) -> int:
    if args.explain:
        code = args.explain.upper()
        text = (data_root() / "docs" / "RULES.md").read_text(encoding="utf-8")
        start = text.find(f"### {code}")
        if start < 0:
            print(f"unknown rule {code}", file=sys.stderr)
            return 2
        end = text.find("\n### ", start + 1)
        print(text[start:end if end > 0 else None].strip())
        return 0
    for code, title in RULES.items():
        print(f"{code}  {title}")
    return 0


def _market_allows(profile: str, market: str | None) -> bool:
    if market is None:
        return True
    if profile == "ext.cn":
        return market.startswith("cn_")
    return True


def _cmd_catalog(args: argparse.Namespace) -> int:
    cat = load_catalog()
    if args.type:
        t = next((x for x in cat["types"] if x["type"] == args.type.upper()), None)
        if t is None:
            print(f"unknown indicator type {args.type}", file=sys.stderr)
            return 2
        print(json.dumps(localized(t, args.lang), ensure_ascii=False, indent=2))
        return 0
    rows = [t for t in cat["types"]
            if (args.profile is None or t["profile"] == args.profile)
            and _market_allows(t["profile"], args.market)
            and (args.search is None or args.search.lower() in json.dumps(t, ensure_ascii=False).lower())]
    rows = [localized(t, args.lang) for t in rows]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for t in rows:
        params = ", ".join(f"{p['key']}={p.get('default', '?')}" for p in t.get("params", []))
        operands = ", ".join(t.get("operandKeys", []))
        sig = params or (f"operands: {operands}" if operands else "")
        print(f"{t['type']:28} {t['profile']:8} {sig}")
        if t.get("summary"):
            print(f"    {t['summary']}")
    print(f"\n{len(rows)} indicator types. Details: alphaspec catalog --type NAME", file=sys.stderr)
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(load_schema(args.kind), ensure_ascii=False, indent=2))
    return 0


def _cmd_examples(args: argparse.Namespace) -> int:
    files = sorted((data_root() / "examples").rglob("*.json"))
    if not args.name:
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            print(f"{f.stem:36} {doc.get('kind'):9} {doc.get('market'):12} {doc.get('title') or doc.get('scoreName')}")
        return 0
    match = [f for f in files if f.stem == args.name or f.stem.startswith(args.name)]
    if not match:
        print(f"no example named {args.name}", file=sys.stderr)
        return 2
    print(match[0].read_text(encoding="utf-8"), end="")
    return 0


_DOCS = {"spec": "SPEC.md", "rules": "RULES.md", "markets": "MARKETS.md", "runtime": "RUNTIME_API.md"}


def _cmd_docs(args: argparse.Namespace) -> int:
    print((data_root() / "docs" / _DOCS[args.name]).read_text(encoding="utf-8"), end="")
    return 0


def _cmd_skill(args: argparse.Namespace) -> int:
    text = (data_root() / "skills" / "alphaspec" / "SKILL.md").read_text(encoding="utf-8")
    if not args.install:
        print(text, end="")
        return 0
    target = Path(args.install).expanduser() / "alphaspec" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"installed {target}")
    return 0


def _client(args: argparse.Namespace) -> Client:
    return Client(base_url=args.base_url, api_key=args.api_key)


def _out(args: argparse.Namespace, obj: Any, human: str) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2) if args.json else human)


def _print_gate(args: argparse.Namespace, gate: dict[str, Any]) -> int:
    if args.json:
        print(json.dumps(gate, ensure_ascii=False, indent=2))
    else:
        verdict = "PASSED" if gate.get("passed") else "NOT PASSED"
        print(f"gate {verdict} (computedBy {gate.get('computedBy')})")
        sample = gate.get("sample") or {}
        if sample:
            line = f"  in-sample {sample.get('inSampleFrom')} ~ {sample.get('inSampleTo')}"
            if sample.get("outOfSampleFrom"):
                line += f" · out-of-sample {sample.get('outOfSampleFrom')} ~ {sample.get('outOfSampleTo')}"
            print(line)
        for c in gate.get("checks", []):
            mark = "✓" if c.get("passed") else "✗"
            metric = c.get("metric") or "actual"
            print(f"  {mark} {c.get('code'):24} {metric}={c.get('actual')} threshold={c.get('threshold')}")
            # Printed for passing checks too: without it a reader guesses what the number is.
            if c.get("hint"):
                print(f"      {c['hint']}")
        trade = gate.get("tradeSettings")
        if trade:
            print("  trade settings used:")
            for block in ("exits", "sizing", "execution"):
                if trade.get(block):
                    print(f"    {block}: {json.dumps(trade[block], ensure_ascii=False)}")
            for d in trade.get("defaults", []):
                print(f"    default {d.get('field')}: {d.get('value')}")
    report = validate(gate)
    if not report.ok:
        print("warning: runtime returned a gate-result that does not match the contract:", file=sys.stderr)
        for i in report.issues:
            print(f"  {i}", file=sys.stderr)
    return 0 if gate.get("passed") else 1


def _cmd_whoami(args: argparse.Namespace) -> int:
    me = _client(args).whoami()
    q = me.get("evaluationQuota") or {}
    quota = f" · evaluations today {q.get('used')}/{q.get('limit')}" if q else ""
    _out(args, me, f"{me.get('username')} · key {me.get('keyId')} · contract {me.get('contractVersion')}{quota}\n"
                   f"  can:    {', '.join(me.get('canDo', []))}\n"
                   f"  cannot: {', '.join(me.get('cannotDo', []))}")
    return 0


def _evaluate_and_wait(args: argparse.Namespace, c: Client, artifact_id: int) -> int:
    started = c.evaluate(artifact_id)
    if not args.wait:
        _out(args, started, f"evaluation {started.get('evaluationId')} {started.get('status')} "
                            f"— poll with: alphaspec result {artifact_id}")
        return 0
    if not args.json:
        print(f"evaluating artifact {artifact_id} (in-sample + out-of-sample backtests) ...", file=sys.stderr)
    return _print_gate(args, c.wait(artifact_id, timeout=args.timeout))


def _cmd_submit(args: argparse.Namespace) -> int:
    doc = json.loads(Path(args.file).read_text(encoding="utf-8"))
    c = _client(args)
    res = c.submit(doc)
    aid = res["artifactId"]
    warnings = res.get("warnings") or []
    if not args.json:
        print(f"submitted: artifact {aid}" + (f" ({len(warnings)} warnings)" if warnings else ""))
        for w in warnings:
            print(f"  WARNING {w.get('code')} at {w.get('path')}: {w.get('message')}")
    elif not (args.evaluate or args.promote):
        print(json.dumps(res, ensure_ascii=False, indent=2))
    if not (args.evaluate or args.promote):
        return 0
    rc = _evaluate_and_wait(argparse.Namespace(**{**vars(args), "wait": True}), c, aid)
    if rc != 0 or not args.promote:
        return rc
    return _promote(args, c, aid)


def _cmd_evaluate(args: argparse.Namespace) -> int:
    return _evaluate_and_wait(args, _client(args), args.artifact_id)


def _cmd_result(args: argparse.Namespace) -> int:
    state, body = _client(args).gate_result(args.artifact_id)
    if state == "DONE":
        return _print_gate(args, body)
    _out(args, body, f"{state}" + (f": {body.get('error')}" if body.get("error") else ""))
    return 1 if state == "FAILED" else 0


def _cmd_list(args: argparse.Namespace) -> int:
    rows = _client(args).list()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for r in rows:
        verdict = "—" if not r.get("evaluated") else ("passed" if r.get("passed") else "not passed")
        print(f"{r.get('artifactId'):>8}  {verdict:11}  {r.get('title')}")
    return 0


def _promote(args: argparse.Namespace, c: Client, artifact_id: int) -> int:
    res = c.promote(artifact_id, getattr(args, "name", None), getattr(args, "target", None))
    if res.get("updated"):
        _out(args, res, f"strategy {res.get('strategyId')} updated to a new version — {res.get('next')}")
        return 0
    what = "created" if res.get("created") else "already exists"
    _out(args, res, f"paper strategy {res.get('strategyId')} {what} (disabled) — {res.get('next')}")
    return 0


def _cmd_capabilities(args: argparse.Namespace) -> int:
    cap = _client(args).capabilities()
    if args.json:
        print(json.dumps(cap, ensure_ascii=False, indent=2))
        return 0
    ev = cap.get("evaluation", {})
    q = ev.get("quota") or {}
    print(f"contract versions {', '.join(cap.get('contractVersions', []))}"
          + (f" · evaluations today {q.get('used')}/{q.get('limit')}" if q else ""))
    for tier in ("daily", "intraday", "factor"):
        w = ev.get(tier) or {}
        if not w:
            continue
        print(f"{tier:8} {' '.join(w.get('timeframes', []))}: in-sample {w.get('inSampleFrom')} ~ "
              f"{w.get('outOfSampleFrom')}, out-of-sample ~ {w.get('to')}")
    print(f"universe modes: {', '.join(ev.get('universeModes', []))} · sizing: {', '.join(ev.get('sizingModes', []))}")
    for m in cap.get("markets", []):
        tiers = m.get("evaluation", {})
        cells = []
        for tier in ("daily", "intraday"):
            t = tiers.get(tier) or {}
            cells.append(f"{tier} {'yes' if t.get('evaluable') else 'no'}")
        promote = "promotable" if m.get("promotable") else "evaluate only"
        bench = (m.get("benchmark") or {}).get("name") or "no benchmark"
        print(f"  {m.get('id'):12} {' · '.join(cells)} · {promote} · {bench} · profiles {', '.join(m.get('indicatorProfiles', []))}")
        for tier in ("daily", "intraday"):
            t = tiers.get(tier) or {}
            if not t.get("evaluable") and t.get("reason"):
                print(f"      {tier}: {t['reason']}")
    return 0


def _cmd_factors(args: argparse.Namespace) -> int:
    res = _client(args).factors()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    q = (args.search or "").lower()
    for f in res.get("factors", []):
        text = " ".join(str(f.get(k) or "") for k in ("factor", "name", "category", "description")).lower()
        if q and q not in text:
            continue
        lock = " [locked]" if f.get("locked") else ""
        print(f"  {f.get('factor'):28} {f.get('source'):6} {f.get('category') or '':10} {f.get('name')}{lock}")
    for sc in res.get("scores", []):
        print(f"  {sc.get('factor'):28} SCORE  {sc.get('market') or '':10} {sc.get('from')} ~ {sc.get('to')} ({sc.get('days')} days)")
    return 0


def _read_docs(paths: list[str]) -> list[dict[str, Any]]:
    """One document per file, a JSON array of documents, or JSON lines."""
    docs: list[dict[str, Any]] = []
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            docs.extend(json.loads(line) for line in text.splitlines() if line.strip())
            continue
        docs.extend(data if isinstance(data, list) else [data])
    return docs


def _cmd_submit_scores(args: argparse.Namespace) -> int:
    res = _client(args).submit_scores(_read_docs(args.files))
    _out(args, res, f"uploaded {res.get('rows')} scores on {res.get('dates')} dates — bind it as "
                    f"\"factor\": \"{res.get('factor')}\"")
    return 0


def _cmd_scores(args: argparse.Namespace) -> int:
    rows = _client(args).scores()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for r in rows:
        print(f"  {r.get('factor'):28} {r.get('market') or '':10} {r.get('from')} ~ {r.get('to')} ({r.get('days')} days)")
    return 0


def _cmd_evidence(args: argparse.Namespace) -> int:
    ev = _client(args).evidence(strategy_id=args.strategy_id, artifact_id=args.artifact,
                                date_from=args.date_from, date_to=args.date_to)
    if args.json:
        print(json.dumps(ev, ensure_ascii=False, indent=2))
        return 0
    w = ev.get("window", {})
    print(f"{ev.get('subject', {}).get('strategy')} · {ev.get('subject', {}).get('mode')} · {w.get('from')} ~ {w.get('to')} ({w.get('timezone')})")
    for p in ev.get("pipeline", []):
        print(f"  pipeline {p.get('stage'):18} {p.get('status')}" + (f"  {'; '.join(p.get('violations', []))}" if p.get("violations") else ""))
    q = ev.get("executionQuality", {})
    print(f"  orders {q.get('orders', 0)} · filled {q.get('fillRatePct', '-')}% · rejected {q.get('rejectRatePct', '-')}%"
          + (f" · slippage avg {q.get('avgSlippageBps')}bp p95 {q.get('p95SlippageBps')}bp ({ev.get('caliber', {}).get('slippageBasis')})"
             if "avgSlippageBps" in q else ""))
    for r in ev.get("rejects", [])[:10]:
        print(f"  reject {r.get('category'):11} {r.get('code'):28} x{r.get('count')}  {r.get('message', '')[:80]}")
    led = ev.get("ledger", [])
    if led:
        print(f"  ledger: {len(led)} fills, last {led[-1].get('ts')} {led[-1].get('side')} {led[-1].get('symbol')}")
    return 0


def _cmd_strategies(args: argparse.Namespace) -> int:
    rows = _client(args).strategies()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for r in rows:
        state = "running" if r.get("enabled") else "stopped"
        print(f"{r.get('strategyId'):>8}  {r.get('market'):11} {r.get('timeframe'):4} {state:8} {r.get('name')}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    doc, issues = _client(args).export_strategy(args.strategy_id)
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    errors = [i for i in issues if str(i.get("severity", "")).lower() == "error"]
    for i in issues:
        print(f"  {str(i.get('severity', '')).upper():7} {i.get('code')} at {i.get('path') or '/'}: {i.get('message')}",
              file=sys.stderr)
    if errors:
        print(f"exported with {len(errors)} error(s): the document does not validate as is", file=sys.stderr)
        return 1
    return 0


def _cmd_promote(args: argparse.Namespace) -> int:
    return _promote(args, _client(args), args.artifact_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alphaspec", description="AlphaSpec: validate documents and talk to a runtime.")
    parser.add_argument("--version", action="version", version=f"alphaspec {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate documents locally")
    v.add_argument("files", nargs="+")
    v.add_argument("--strict", action="store_true", help="treat warnings as failures")
    v.add_argument("--json", action="store_true", help="one JSON line per file")
    v.set_defaults(func=_cmd_validate)

    r = sub.add_parser("rules", help="list lint rules")
    r.add_argument("--explain", metavar="CODE", help="print why a rule exists and how to fix it")
    r.set_defaults(func=_cmd_rules)

    c = sub.add_parser("catalog", help="indicator types you may use")
    c.add_argument("--market", help="only types usable on this market (e.g. us_equity hides China-only types)")
    c.add_argument("--profile", choices=["core", "ext.cn", "ext.l2", "ext.data"])
    c.add_argument("--search", help="substring match on name, summary and parameters")
    c.add_argument("--type", help="full entry for one type")
    c.add_argument("--lang", choices=["en", "zh"], default=default_lang(),
                   help="language of descriptions (default: $ALPHASPEC_LANG, else from the locale)")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=_cmd_catalog)

    sc = sub.add_parser("schema", help="print a JSON Schema")
    sc.add_argument("kind", choices=["artifact", "score", "gate-result", "evidence", "capabilities", "common"])
    sc.set_defaults(func=_cmd_schema)

    ex = sub.add_parser("examples", help="list or print example documents")
    ex.add_argument("name", nargs="?")
    ex.set_defaults(func=_cmd_examples)

    dc = sub.add_parser("docs", help="print a reference document")
    dc.add_argument("name", choices=sorted(_DOCS))
    dc.set_defaults(func=_cmd_docs)

    sk = sub.add_parser("skill", help="print or install the Agent Skill")
    sk.add_argument("--install", metavar="DIR",
                    help="skills directory, e.g. ~/.claude/skills (writes DIR/alphaspec/SKILL.md)")
    sk.set_defaults(func=_cmd_skill)

    remote = argparse.ArgumentParser(add_help=False)
    remote.add_argument("--base-url", help="runtime base URL (default: $ALPHASPEC_BASE_URL)")
    remote.add_argument("--api-key", help="API key (default: $ALPHASPEC_API_KEY)")
    remote.add_argument("--json", action="store_true", help="machine-readable output")

    w = sub.add_parser("whoami", parents=[remote], help="check the API key")
    w.set_defaults(func=_cmd_whoami)

    s = sub.add_parser("submit", parents=[remote], help="submit an artifact")
    s.add_argument("file")
    s.add_argument("--evaluate", action="store_true", help="start an evaluation after submitting and wait for it")
    s.add_argument("--promote", action="store_true", help="also turn it into a paper strategy if the gate passes")
    s.add_argument("--name", help="strategy name for --promote (default: document title)")
    s.add_argument("--timeout", type=float, default=900, help="seconds to wait for the evaluation")
    s.set_defaults(func=_cmd_submit)

    e = sub.add_parser("evaluate", parents=[remote], help="start a platform evaluation")
    e.add_argument("artifact_id", type=int)
    e.add_argument("--wait", action="store_true", help="wait for the gate result")
    e.add_argument("--timeout", type=float, default=900)
    e.set_defaults(func=_cmd_evaluate)

    g = sub.add_parser("result", parents=[remote], help="show the latest gate result")
    g.add_argument("artifact_id", type=int)
    g.set_defaults(func=_cmd_result)

    lst = sub.add_parser("list", parents=[remote], help="list my submissions")
    lst.set_defaults(func=_cmd_list)

    p = sub.add_parser("promote", parents=[remote], help="turn a gate-passed artifact into a paper strategy")
    p.add_argument("artifact_id", type=int)
    p.add_argument("--name")
    p.add_argument("--target", type=int, metavar="STRATEGY_ID",
                   help="publish as a new version of this existing strategy instead of creating one")
    p.set_defaults(func=_cmd_promote)

    cp = sub.add_parser("capabilities", parents=[remote], help="what the runtime can evaluate now")
    cp.set_defaults(func=_cmd_capabilities)

    st = sub.add_parser("strategies", parents=[remote], help="my existing strategies on the runtime")
    st.set_defaults(func=_cmd_strategies)

    fc = sub.add_parser("factors", parents=[remote], help="factors I can bind, and my score series")
    fc.add_argument("--search", help="substring match on code, name, category, description")
    fc.set_defaults(func=_cmd_factors)

    ss = sub.add_parser("submit-scores", parents=[remote], help="upload score documents")
    ss.add_argument("files", nargs="+", help="score documents: one per file, a JSON array, or JSON lines")
    ss.set_defaults(func=_cmd_submit_scores)

    sl = sub.add_parser("scores", parents=[remote], help="my uploaded score series")
    sl.set_defaults(func=_cmd_scores)

    ev = sub.add_parser("evidence", parents=[remote], help="what happened when a strategy ran")
    ev.add_argument("strategy_id", type=int, nargs="?")
    ev.add_argument("--artifact", type=int, help="the strategy this artifact was promoted to")
    ev.add_argument("--from", dest="date_from", help="YYYY-MM-DD, market-local (default: 30 days before --to)")
    ev.add_argument("--to", dest="date_to", help="YYYY-MM-DD, market-local (default: today)")
    ev.set_defaults(func=_cmd_evidence)

    xp = sub.add_parser("export", parents=[remote], help="export an existing strategy as an AlphaSpec artifact")
    xp.add_argument("strategy_id", type=int)
    xp.add_argument("-o", "--output", help="write to this file instead of stdout")
    xp.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Rejected as exc:
        print(f"rejected: {len(exc.issues)} issue(s)", file=sys.stderr)
        for i in exc.issues:
            print(f"  {i.get('severity', 'error').upper():7} {i.get('code')} at {i.get('path') or '/'}: {i.get('message')}",
                  file=sys.stderr)
        return 1
    except EvaluationFailed as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (AlphaSpecError, OSError, TimeoutError) as exc:
        print(f"runtime error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
