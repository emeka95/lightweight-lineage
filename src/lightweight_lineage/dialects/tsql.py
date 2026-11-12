"""T-SQL object and data-flow extraction."""

from __future__ import annotations

from sqlfluff.core import Linter

from lightweight_lineage.analysis_core import (
    GraphBuilder,
    ParsedFile,
    add_bulk_insert_flows,
    add_dml_flows,
    add_procedure_calls,
    add_view_flows,
    descendants,
    first_direct,
    procedure_spans,
)
from lightweight_lineage.dialects.base import DialectAdapter, ObjectDeclaration


class TSqlAdapter(DialectAdapter):
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
        for synonym in descendants(
            parsed_file.tree,
            "create_synonym_statement",
        ):
            synonym_name = first_direct(synonym, "synonym_reference")
            target = first_direct(synonym, "object_reference")
            if synonym_name is None or target is None:
                continue
            builder.add_synonym(synonym_name.raw, target.raw)

    def extract_flows(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
        _linter: Linter,
    ) -> None:
        spans = procedure_spans(parsed_file, builder)
        add_view_flows(parsed_file, builder)
        add_dml_flows(parsed_file, builder, spans)
        add_bulk_insert_flows(parsed_file, builder, spans)
        add_procedure_calls(parsed_file, builder, spans)


__all__ = ["TSqlAdapter"]
