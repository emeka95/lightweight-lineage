"""Shared protocol for SQL dialect extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lightweight_lineage.analysis_core import GraphBuilder


ObjectDeclaration = tuple[str, str, str]


class ParsedFile(Protocol):
    """Dialect-neutral handle for successfully parsed input."""

    path: str


@dataclass(frozen=True, slots=True)
class ParseDiagnostic:
    severity: str
    code: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class ParseResult:
    parsed_file: ParsedFile | None
    diagnostics: tuple[ParseDiagnostic, ...] = ()


class DialectAdapter(Protocol):
    """Dialect-specific declarations and flow extraction."""

    source_extensions: tuple[str, ...]
    object_declarations: tuple[ObjectDeclaration, ...]

    def parse(self, source: str, path: str) -> ParseResult: ...

    def collect_declarations(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None: ...

    def collect_metadata(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        return None

    def extract_flows(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None: ...


__all__ = [
    "DialectAdapter",
    "ObjectDeclaration",
    "ParseDiagnostic",
    "ParseResult",
    "ParsedFile",
]
