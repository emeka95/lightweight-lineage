"""Shared protocol for SQL dialect extraction adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlfluff.core import Linter

if TYPE_CHECKING:
    from lightweight_lineage.analysis import _GraphBuilder, _ParsedFile


ObjectDeclaration = tuple[str, str, str]


class DialectAdapter(Protocol):
    """Dialect-specific declarations and flow extraction."""

    object_declarations: tuple[ObjectDeclaration, ...]

    def collect_metadata(
        self,
        parsed_file: _ParsedFile,
        builder: _GraphBuilder,
    ) -> None: ...

    def extract_flows(
        self,
        parsed_file: _ParsedFile,
        builder: _GraphBuilder,
        linter: Linter,
    ) -> None: ...


__all__ = ["DialectAdapter", "ObjectDeclaration"]
