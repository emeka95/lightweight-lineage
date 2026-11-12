"""T-SQL object and data-flow extraction."""

from __future__ import annotations

from sqlfluff.core import Linter

from lightweight_lineage.analysis_core import (
    GraphBuilder,
    SqlParsedFile,
    add_bulk_insert_flows,
    add_dml_flows,
    add_procedure_calls,
    add_view_flows,
    collect_object_declarations,
    descendants,
    first_direct,
    parse_sql_source,
    procedure_spans,
    require_sql_parsed_file,
)
from lightweight_lineage.dialects.base import (
    DialectAdapter,
    ObjectDeclaration,
    ParseResult,
    ParsedFile,
)


class TSqlAdapter(DialectAdapter):
    source_extensions: tuple[str, ...] = (".sql",)
    object_declarations: tuple[ObjectDeclaration, ...] = (
        ("create_table_statement", "table", "table_reference"),
        ("create_view_statement", "view", "object_reference"),
        ("create_procedure_statement", "stored_procedure", "object_reference"),
    )

    def __init__(self) -> None:
        self._linter = Linter(dialect="tsql")

    def parse(self, source: str, path: str) -> ParseResult:
        return parse_sql_source(source, path, self._linter)

    def collect_declarations(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        sql_file = require_sql_parsed_file(parsed_file)
        collect_object_declarations(
            sql_file,
            builder,
            self.object_declarations,
        )

    def collect_metadata(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        sql_file: SqlParsedFile = require_sql_parsed_file(parsed_file)
        for synonym in descendants(
            sql_file.tree,
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
    ) -> None:
        sql_file = require_sql_parsed_file(parsed_file)
        spans = procedure_spans(sql_file, builder)
        add_view_flows(sql_file, builder)
        add_dml_flows(sql_file, builder, spans)
        add_bulk_insert_flows(sql_file, builder, spans)
        add_procedure_calls(sql_file, builder, spans)


__all__ = ["TSqlAdapter"]
