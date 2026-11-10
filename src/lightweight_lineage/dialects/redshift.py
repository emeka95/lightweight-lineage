"""Amazon Redshift object and data-flow extraction."""

from __future__ import annotations

import re

from sqlfluff.core import Linter
from sqlfluff.core.parser import BaseSegment

from lightweight_lineage.analysis_core import (
    GraphBuilder as _GraphBuilder,
    ParsedFile as _ParsedFile,
    Reference as _Reference,
    _add_data_flow,
    _add_dml_flows,
    _descendants,
    _location,
    _literal_value,
    _normalized_name,
    _reference,
    _resolve_endpoint,
    _statement_identifier,
    _table_references,
)
from lightweight_lineage.dialects.base import ObjectDeclaration

_REDSHIFT_DYNAMIC_EXECUTE = re.compile(
    r"(?im)^[ \t]*EXECUTE(?:[ \t]+IMMEDIATE)?[ \t]+"
    r"'(?:''|[^'])*'[ \t]*(?:USING\b[^;\r\n]*)?;?"
)


def _redshift_procedure_body(
    procedure: BaseSegment,
    file: str,
    builder: _GraphBuilder,
    linter: Linter,
) -> tuple[str, BaseSegment] | None:
    name_segment = next(
        (child for child in procedure.segments if child.get_type() == "function_name"),
        None,
    )
    definition = next(
        (
            child
            for child in procedure.segments
            if child.get_type() == "function_definition"
        ),
        None,
    )
    if name_segment is None or definition is None:
        return None

    name = name_segment.raw
    identifier = next(
        (
            object_id
            for object_id in builder.declarations.get(_normalized_name(name), [])
            if builder.objects[object_id].type == "stored_procedure"
        ),
        None,
    )
    if identifier is None:
        return None

    match = re.search(
        r"\bAS\s+(\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$)(.*?)\1",
        definition.raw,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        line, column = _location(definition)
        builder.add_diagnostic(
            "warning",
            "unsupported_procedure_body",
            file,
            f"Stored procedure {name!r} does not use a supported dollar-quoted body.",
            line,
            column,
        )
        return None

    function_line, _ = _location(definition)
    body_line = function_line + definition.raw[: match.start(2)].count("\n")
    body = match.group(2)
    masked_body = list(body)
    for dynamic_statement in _REDSHIFT_DYNAMIC_EXECUTE.finditer(body):
        prefix = body[: dynamic_statement.start()]
        line = body_line + prefix.count("\n")
        column = len(prefix.rsplit("\n", 1)[-1]) + 1
        builder.add_diagnostic(
            "warning",
            "unsupported_dynamic_sql",
            file,
            "Dynamic SQL in a Redshift stored procedure is not analyzed.",
            line,
            column,
        )
        for index in range(dynamic_statement.start(), dynamic_statement.end()):
            if masked_body[index] not in "\r\n":
                masked_body[index] = " "
    body = "".join(masked_body)
    begin = re.search(r"\bBEGIN\b", body, re.IGNORECASE)
    end = re.search(r"\bEND\s*;?\s*$", body, re.IGNORECASE)
    if begin is None or end is None or begin.end() > end.start():
        line, column = _location(definition)
        builder.add_diagnostic(
            "warning",
            "unsupported_procedure_body",
            file,
            f"Stored procedure {name!r} does not contain a supported BEGIN/END body.",
            line,
            column,
        )
        return None

    body_source = (
        "\n" * (body_line - 1)
        + body[: begin.start()]
        + " " * (begin.end() - begin.start())
        + body[begin.end() : end.start()]
        + " " * (end.end() - end.start())
        + body[end.end() :]
    )
    parsed = linter.parse_string(body_source, fname=file)
    if parsed.violations:
        for violation in parsed.violations:
            builder.add_diagnostic(
                "error",
                "sql_parse_error",
                file,
                str(violation),
                getattr(violation, "line_no", None),
                getattr(violation, "line_pos", None),
            )
        return None
    return identifier, parsed.tree


def _add_redshift_view_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> None:
    for view in _descendants(
        parsed_file.tree,
        "create_view_statement",
        "create_materialized_view_statement",
    ):
        name_segment = _statement_identifier(view, "table_reference", "object_reference")
        if name_segment is None:
            continue
        line, column = _location(name_segment)
        targets = builder.declared_resolutions(
            name_segment.raw,
            parsed_file.path,
            line,
            column,
        )
        _add_data_flow(
            builder,
            _table_references(view, parsed_file.path),
            targets,
            parsed_file.path,
        )


def _add_redshift_ctas_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> None:
    for statement in _descendants(parsed_file.tree, "create_table_as_statement"):
        target_segment = _statement_identifier(statement, "object_reference")
        if target_segment is None:
            continue
        target_reference = _reference(target_segment, parsed_file.path, "table")
        targets = builder.declared_resolutions(
            target_reference.name,
            parsed_file.path,
            target_reference.line,
            target_reference.column,
        )
        _add_data_flow(
            builder,
            _table_references(statement, parsed_file.path),
            targets,
            parsed_file.path,
        )


def _add_redshift_external_table_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> None:
    for statement in _descendants(parsed_file.tree, "create_external_table_statement"):
        target_segment = _statement_identifier(statement, "table_reference")
        location = _statement_identifier(statement, "quoted_literal")
        if target_segment is None or location is None:
            continue
        target_reference = _reference(
            target_segment,
            parsed_file.path,
            "external_table",
        )
        source_reference = _Reference(
            _literal_value(location.raw),
            parsed_file.path,
            *_location(location),
            "data_file",
        )
        _add_data_flow(
            builder,
            [source_reference],
            _resolve_endpoint(builder, target_reference, write_target=True),
            parsed_file.path,
        )


def _add_redshift_copy_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
) -> None:
    for statement in _descendants(parsed_file.tree, "copy_statement"):
        target_segment = _statement_identifier(statement, "table_reference")
        source_segment = _statement_identifier(statement, "quoted_literal")
        if target_segment is None or source_segment is None:
            continue
        target = _reference(target_segment, parsed_file.path, "table")
        source = _Reference(
            _literal_value(source_segment.raw),
            parsed_file.path,
            *_location(source_segment),
            "data_file",
        )
        _add_data_flow(
            builder,
            [source],
            _resolve_endpoint(builder, target, write_target=True),
            parsed_file.path,
        )


def _add_redshift_unload_flows(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
    linter: Linter,
) -> None:
    for statement in _descendants(parsed_file.tree, "unload_statement"):
        query_container = _statement_identifier(statement, "bracketed")
        output_segment = _statement_identifier(statement, "quoted_literal")
        query_literal = (
            next(iter(_descendants(query_container, "quoted_literal")), None)
            if query_container is not None
            else None
        )
        if query_literal is None or output_segment is None:
            continue

        parsed_query = linter.parse_string(
            _literal_value(query_literal.raw),
            fname=parsed_file.path,
        )
        if parsed_query.violations:
            for violation in parsed_query.violations:
                builder.add_diagnostic(
                    "error",
                    "sql_parse_error",
                    parsed_file.path,
                    str(violation),
                    getattr(violation, "line_no", None),
                    getattr(violation, "line_pos", None),
                )
            continue

        output = _Reference(
            _literal_value(output_segment.raw),
            parsed_file.path,
            *_location(output_segment),
            "data_file",
        )
        target = _resolve_endpoint(builder, output, write_target=True)
        query_line_offset = _location(query_literal)[0] - 1
        sources = [
            _Reference(
                reference.name,
                reference.file,
                reference.line + query_line_offset,
                reference.column,
                reference.type_hint,
            )
            for reference in _table_references(parsed_query.tree, parsed_file.path)
        ]
        _add_data_flow(builder, sources, target, parsed_file.path)


def _add_redshift_procedure_calls(
    parsed_file: _ParsedFile,
    builder: _GraphBuilder,
    caller_id: str,
) -> None:
    for statement in _descendants(parsed_file.tree, "call_statement"):
        function = next(
            (child for child in statement.segments if child.get_type() == "function"),
            None,
        )
        match = re.match(r"\s*([^\s(]+)", function.raw) if function is not None else None
        if match is None:
            continue

        reference = _reference(function, parsed_file.path, "stored_procedure")
        reference = _Reference(
            match.group(1),
            reference.file,
            reference.line,
            reference.column,
            reference.type_hint,
        )
        caller = builder.objects.get(caller_id)
        if caller is None:
            continue
        for callee in builder.resolve(reference):
            status = "ambiguous" if callee.status == "ambiguous" else (
                "unknown_target" if callee.status == "unknown" else "confirmed"
            )
            builder.add_edge(
                caller,
                callee.node,
                "procedure_call",
                status,
                parsed_file.path,
                reference.line,
                reference.column,
            )


class RedshiftAdapter:
    object_declarations: tuple[ObjectDeclaration, ...] = (
        ("create_table_statement", "table", "table_reference"),
        ("create_table_as_statement", "table", "object_reference"),
        ("create_view_statement", "view", "table_reference"),
        ("create_materialized_view_statement", "materialized_view", "table_reference"),
        ("create_external_table_statement", "external_table", "table_reference"),
        ("create_procedure_statement", "stored_procedure", "function_name"),
    )

    def collect_metadata(
        self,
        _parsed_file: _ParsedFile,
        _builder: _GraphBuilder,
    ) -> None:
        pass

    def extract_flows(
        self,
        parsed_file: _ParsedFile,
        builder: _GraphBuilder,
        linter: Linter,
    ) -> None:
        _add_redshift_view_flows(parsed_file, builder)
        _add_redshift_ctas_flows(parsed_file, builder)
        _add_redshift_external_table_flows(parsed_file, builder)
        _add_redshift_copy_flows(parsed_file, builder)
        _add_redshift_unload_flows(parsed_file, builder, linter)

        procedures = _descendants(parsed_file.tree, "create_procedure_statement")
        for procedure in procedures:
            body = _redshift_procedure_body(
                procedure,
                parsed_file.path,
                builder,
                linter,
            )
            if body is None:
                continue
            procedure_id, body_tree = body
            procedure_file = _ParsedFile(parsed_file.path, body_tree)
            _add_dml_flows(procedure_file, builder, [], procedure_id)
            _add_redshift_procedure_calls(procedure_file, builder, procedure_id)

        _add_dml_flows(parsed_file, builder, [])


__all__ = ["RedshiftAdapter"]
