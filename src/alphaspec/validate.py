"""Validate AlphaSpec documents: JSON Schema first, then semantic lint rules.

Schema validation answers "is this well-formed". Lint rules answer "will this do what
its author thinks": unresolved references, look-ahead, indicators that cannot exist on
this market, and similar mistakes that a runtime would otherwise accept and run wrongly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ._resources import CONTRACT_VERSION, SUPPORTED_VERSIONS, load_schema, schema_dir

KINDS = ("artifact", "score", "gate-result", "evidence")


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # "error" | "warning"
    path: str
    message: str
    hint: str = ""

    def __str__(self) -> str:
        loc = self.path or "/"
        tail = f"  hint: {self.hint}" if self.hint else ""
        return f"{self.severity.upper():7} {self.code} at {loc}: {self.message}{tail}"


@dataclass
class Report:
    kind: str | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> list[str]:
        return sorted({i.code for i in self.issues})


def _registry(version: str) -> Registry:
    resources = []
    for path in sorted(schema_dir(version).glob("*.schema.json")):
        name = path.name.removesuffix(".schema.json")
        doc = load_schema(name, version)
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def _validator(kind: str, version: str = CONTRACT_VERSION) -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(kind, version),
        registry=_registry(version),
        format_checker=FormatChecker(),
    )


def _pointer(parts) -> str:
    return "".join(f"/{p}" for p in parts)


def _schema_issues(doc: Any, kind: str, version: str) -> list[Issue]:
    validator = _validator(kind, version)
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        # oneOf / anyOf failures are reported as a single opaque message; surface the
        # most specific sub-error instead so the author sees which field is wrong.
        best = err
        if err.context:
            best = min(err.context, key=lambda e: (-len(e.absolute_path), len(e.message)))
        out.append(Issue("SCHEMA", "error", _pointer(best.absolute_path), best.message))
    return out


def validate(doc: Any, kind: str | None = None) -> Report:
    """Validate one document. kind is read from doc['kind'] when not given."""
    if kind is None and isinstance(doc, dict):
        kind = doc.get("kind")
    if kind not in KINDS:
        return Report(kind, [Issue("UNKNOWN_KIND", "error", "/kind",
                                   f"kind must be one of {', '.join(KINDS)}, got {kind!r}")])
    version = doc.get("contractVersion") if isinstance(doc, dict) else None
    if version is not None and version not in SUPPORTED_VERSIONS:
        return Report(kind, [Issue("UNSUPPORTED_VERSION", "error", "/contractVersion",
                                   f"this validator understands contractVersion {', '.join(SUPPORTED_VERSIONS)}, "
                                   f"got {version!r}")])

    report = Report(kind, _schema_issues(doc, kind, version or CONTRACT_VERSION))
    if report.errors:
        # Lint rules assume a well-formed document.
        return report

    from . import lints
    report.issues.extend(lints.run(doc, kind))
    return report
