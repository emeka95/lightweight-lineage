"""T-SQL object and data-flow extraction."""

from __future__ import annotations

from sqlfluff.core import Linter

from lightweight_lineage.analysis_core import (
    GraphBuilder,
    ParsedFile,
    _add_bulk_insert_flows,
    _add_dml_flows,
    _add_procedure_calls,
    _add_view_flows,
    _descendants,
    _first_direct,
    _normalized_name,
    _procedure_spans,
)
from lightweight_lineage.dialects.base import ObjectDeclaration


class TSqlAdapter:
    object_declarations: tuple[ObjectDeclaration, ...] = (
        ("create_table_statement", "table", "table_reference"),
        ("create_view_statement", "view", "object_reference"),
        ("create_procedure_statement", "stored_procedure", "object_reference"),
    )

    def collect_metadata(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        for synonym in _descendants(
            parsed_file.tree,
            "create_synonym_statement",
        ):
            synonym_name = _first_direct(synonym, "synonym_reference")
            target = _first_direct(synonym, "object_reference")
            if synonym_name is None or target is None:
                continue
            synonym_key = _normalized_name(synonym_name.raw)
            targets = builder.synonyms.setdefault(synonym_key, [])
            if _normalized_name(target.raw) not in {
                _normalized_name(value) for value in targets
            }:
                targets.append(target.raw)

    def extract_flows(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
        _linter: Linter,
    ) -> None:
        procedure_spans = _procedure_spans(parsed_file, builder)
        _add_view_flows(parsed_file, builder)
        _add_dml_flows(parsed_file, builder, procedure_spans)
        _add_bulk_insert_flows(parsed_file, builder, procedure_spans)
        _add_procedure_calls(parsed_file, builder, procedure_spans)


__all__ = ["TSqlAdapter"]
