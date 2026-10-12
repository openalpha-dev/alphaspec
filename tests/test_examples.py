import json
import re
from pathlib import Path

import pytest

from alphaspec import validate
from alphaspec.lints import RULES

ROOT = Path(__file__).parent.parent
EXAMPLES = sorted((ROOT / "examples").rglob("*.json"))


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_examples_are_clean(path):
    report = validate(json.loads(path.read_text(encoding="utf-8")))
    assert report.issues == [], "\n".join(str(i) for i in report.issues)


def test_every_rule_is_documented():
    doc = (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")
    missing = [code for code in RULES if not re.search(rf"^###\s+{code}\b", doc, re.M)]
    assert not missing, f"undocumented rules: {missing}"


def test_every_rule_has_a_conformance_case():
    names = " ".join(p.stem for p in (ROOT / "conformance" / "cases").glob("*.json"))
    missing = [code for code in RULES if code.lower() not in names]
    assert not missing, f"rules without a conformance case: {missing}"


def test_gate_result_03_with_trade_settings_validates():
    from alphaspec import validate
    gate = {
        "contractVersion": "0.3", "kind": "gate-result", "passed": False, "computedBy": "PLATFORM",
        "checks": [{"code": "GATE_MIN_SHARPE", "metric": "sharpe", "passed": False, "actual": 0.3, "threshold": 0.8}],
        "tradeSettings": {
            "exits": {"stopLossPct": 8},
            "execution": {"fillTiming": "NEXT_OPEN"},
            "defaults": [{"field": "/sizing", "value": "runtime default: each entry buys as much as maxOrderNotional ..."},
                         {"field": "/execution/fillTiming", "value": "NEXT_OPEN"}],
        },
    }
    assert validate(gate).ok, validate(gate).issues
    gate["tradeSettings"]["exits"] = {"stopLossPct": 0}
    assert not validate(gate).ok
    # 0.2 gate-results have no tradeSettings
    gate["contractVersion"] = "0.2"
    gate["tradeSettings"]["exits"] = {"stopLossPct": 8}
    assert not validate(gate).ok
