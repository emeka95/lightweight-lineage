"""Project-owned lineage graph types and deterministic serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LineageObject:
    id: str
    type: str
    name: str
    status: str
    source_file: str | None = None
    parse_status: str | None = None
    referenced_in: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "status": self.status,
        }
        if self.parse_status is not None:
            result["parse_status"] = self.parse_status
        if self.source_file is not None:
            result["source_file"] = self.source_file
        if self.referenced_in:
            result["referenced_in"] = sorted(self.referenced_in)
        return result


@dataclass(slots=True)
class LineageEdge:
    source: str
    target: str
    kind: str
    status: str
    evidence_file: str
    line: int
    column: int
    via_procedure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "status": self.status,
            "evidence_file": self.evidence_file,
            "line": self.line,
            "column": self.column,
        }
        if self.via_procedure is not None:
            result["via_procedure"] = self.via_procedure
        return result


@dataclass(slots=True)
class Diagnostic:
    severity: str
    code: str
    file: str
    message: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "file": self.file,
            "message": self.message,
        }
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        return result


@dataclass(slots=True)
class LineageGraph:
    objects: list[LineageObject]
    edges: list[LineageEdge]
    diagnostics: list[Diagnostic]

    def to_dict(self) -> dict[str, Any]:
        diagnostics = sorted(
            self.diagnostics,
            key=lambda item: (
                item.file.casefold(),
                item.line or 0,
                item.code,
                item.message,
            ),
        )
        has_errors = any(item.severity == "error" for item in diagnostics)
        has_warnings = any(item.severity == "warning" for item in diagnostics)
        if has_errors:
            run_status = "completed_with_errors"
        elif has_warnings:
            run_status = "completed_with_warnings"
        else:
            run_status = "completed"

        return {
            "schema_version": 1,
            "run_status": run_status,
            "objects": [
                item.to_dict()
                for item in sorted(self.objects, key=lambda item: (item.id.casefold(), item.id))
            ],
            "edges": [
                item.to_dict()
                for item in sorted(
                    self.edges,
                    key=lambda item: (
                        item.target.casefold(),
                        item.source.casefold(),
                        item.kind,
                        item.status,
                        item.evidence_file.casefold(),
                        item.line,
                    ),
                )
            ],
            "diagnostics": [item.to_dict() for item in diagnostics],
            "notes": [
                "Foreign-key declarations are schema relationships, not data-flow edges, so they are not included in the lineage graph.",
                "SQL parsing reports syntax errors; it does not validate database-specific semantic rules.",
            ],
        }


__all__ = ["Diagnostic", "LineageEdge", "LineageGraph", "LineageObject"]
