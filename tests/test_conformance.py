"""Run every conformance case. Any runtime claiming AlphaSpec 0.1 support must
produce the same accept/reject decision and the same rule codes for these files."""
import json
from pathlib import Path

import pytest

from alphaspec import validate

CASES = sorted((Path(__file__).parent.parent / "conformance" / "cases").glob("*.json"))


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(path):
    case = json.loads(path.read_text(encoding="utf-8"))
    report = validate(case["document"])
    expect = case["expect"]
    got_errors = sorted({i.code for i in report.errors})
    got_warnings = sorted({i.code for i in report.warnings})
    detail = "\n".join(str(i) for i in report.issues)
    assert report.ok == expect["valid"], detail
    assert got_errors == expect["errors"], detail
    assert got_warnings == expect["warnings"], detail
