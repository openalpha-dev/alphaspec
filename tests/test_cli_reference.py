"""The reference commands an installed Agent Skill relies on."""
import re
from pathlib import Path

import pytest

from alphaspec.cli import main

ROOT = Path(__file__).parent.parent


def test_catalog_type_shows_semantics(capsys):
    assert main(["catalog", "--type", "DAY_HIGH"]) == 0
    out = capsys.readouterr().out
    assert '"summary"' in out and "DAY_HIGH_BEFORE" in out  # the pitfall that close > DAY_HIGH never holds


def test_catalog_market_filter_hides_china_only_types(capsys):
    main(["catalog", "--market", "us_equity", "--json"])
    us = capsys.readouterr().out
    main(["catalog", "--market", "cn_stock", "--json"])
    cn = capsys.readouterr().out
    assert '"LIMIT_UP_DAYS"' not in us and '"LIMIT_UP_DAYS"' in cn


def test_every_catalog_entry_has_a_summary():
    from alphaspec import load_catalog
    missing = [t["type"] for t in load_catalog()["types"] if not t.get("summary")]
    assert not missing


def test_examples_docs_schema_and_explain(capsys):
    assert main(["examples"]) == 0
    assert main(["examples", "01-ema-cross"]) == 0
    assert main(["docs", "runtime"]) == 0
    assert main(["schema", "gate-result"]) == 0
    assert main(["rules", "--explain", "as011"]) == 0
    out = capsys.readouterr().out
    assert "### AS011" in out and "gate-result" in out
    assert main(["rules", "--explain", "AS999"]) == 2


def _commands_used(name):
    skill = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return set(re.findall(r"`alphaspec ([a-z][a-z-]*)", skill)) | set(re.findall(r"^\s*alphaspec ([a-z][a-z-]*)", skill, re.M))


@pytest.mark.parametrize("name", ["alphaspec", "alphaspec-diagnose"])
def test_commands_named_in_skill_exist(name):
    used = _commands_used(name)
    for cmd in sorted(used):
        with pytest.raises(SystemExit) as e:
            main([cmd, "--help"])
        assert e.value.code == 0, cmd
    expected = {"catalog", "validate", "submit", "examples", "rules"} if name == "alphaspec" else {"strategies", "evidence", "result"}
    assert expected <= used


@pytest.mark.parametrize("name", ["alphaspec", "alphaspec-diagnose"])
def test_skill_has_frontmatter_named_after_its_directory(name):
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert f"name: {name}\n" in head and "description: " in head


def test_skill_install_writes_every_bundled_skill(tmp_path, capsys):
    assert main(["skill", "--install", str(tmp_path)]) == 0
    for name in ("alphaspec", "alphaspec-diagnose"):
        written = (tmp_path / name / "SKILL.md").read_text(encoding="utf-8")
        assert written == (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_skill_prints_by_name_and_rejects_unknown(capsys):
    assert main(["skill", "alphaspec-diagnose"]) == 0
    assert "name: alphaspec-diagnose" in capsys.readouterr().out
    assert main(["skill", "nope"]) == 2


def test_every_catalog_text_has_an_english_translation():
    """i18n/en.json is keyed by the Chinese text: a changed or new description shows up here."""
    import json
    from alphaspec import load_catalog
    en = json.loads((ROOT / "catalog" / "i18n" / "en.json").read_text(encoding="utf-8"))
    missing = []
    for t in load_catalog()["types"]:
        texts = [t.get("labels", {}).get("zh"), t.get("summary"), *t.get("pitfalls", []),
                 *(p.get("description") for p in t["params"])]
        missing += [x for x in texts if x and x not in en]
        assert "en" in t and t["labels"].get("en"), t["type"]
    assert not missing, f"{len(missing)} untranslated, run tools/export_indicator_catalog.py after adding them"


def test_catalog_english_by_flag(capsys):
    assert main(["catalog", "--type", "DONCHIAN_UPPER", "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "excluding it" in out and "唐奇安" not in out
    assert main(["catalog", "--search", "moving average", "--lang", "en", "--json"]) == 0
    assert '"SMA"' in capsys.readouterr().out
