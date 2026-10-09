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
