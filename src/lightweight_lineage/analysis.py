"""Repository parsing and dialect-dispatched lineage analysis."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateError, TemplateRuntimeError
from sqlfluff.core import Linter

from lightweight_lineage.analysis_core import (
    GraphBuilder,
    ParsedFile,
    _descendants,
    _statement_identifier,
)
from lightweight_lineage.graph import LineageGraph
from lightweight_lineage.options import ScanOptions
from lightweight_lineage.scanner import ScanDeadline, scan_repository


def _jinja_ref(*arguments: str) -> str:
    if len(arguments) not in (1, 2) or any(
        not isinstance(argument, str) or not argument.strip()
        for argument in arguments
    ):
        raise TemplateRuntimeError("ref() expects a model name and optional package name.")
    return arguments[-1].strip()


def _jinja_source(*arguments: str) -> str:
    if len(arguments) != 2 or any(
        not isinstance(argument, str) or not argument.strip()
        for argument in arguments
    ):
        raise TemplateRuntimeError("source() expects a source name and a table name.")
    return ".".join(argument.strip() for argument in arguments)


def analyze_repository(
    options: ScanOptions,
    *,
    deadline: ScanDeadline | None = None,
) -> LineageGraph:
    """Parse a repository and return deterministic object-level lineage."""
    from lightweight_lineage.dialects import get_dialect_adapter

    deadline = deadline or ScanDeadline.start(options.timeout_seconds)
    files = scan_repository(options.source, deadline=deadline)
    builder = GraphBuilder(options.mappings, deadline)
    adapter = get_dialect_adapter(options.dialect)
    environment = Environment(undefined=StrictUndefined, autoescape=False)
    environment.globals.update({"ref": _jinja_ref, "source": _jinja_source})
    template_values = {
        variable.name: variable.value for variable in options.template_variables
    }
    linter = Linter(dialect=options.dialect)
    parsed_files: list[ParsedFile] = []

    for path in files:
        deadline.check()
        try:
            source = (options.source / Path(path)).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            builder.add_diagnostic(
                "error",
                "file_read_error",
                path,
                str(error),
            )
            continue

        deadline.check()
        try:
            rendered = environment.from_string(source).render(**template_values)
        except TemplateError as error:
            builder.add_diagnostic(
                "error",
                "template_error",
                path,
                str(error),
                getattr(error, "lineno", None),
            )
            continue

        deadline.check()
        parsed = linter.parse_string(rendered, fname=path)
        deadline.check()
        if parsed.violations:
            for violation in parsed.violations:
                builder.add_diagnostic(
                    "error",
                    "sql_parse_error",
                    path,
                    str(violation),
                    getattr(violation, "line_no", None),
                    getattr(violation, "line_pos", None),
                )
            continue
        parsed_files.append(ParsedFile(path, parsed.tree))

    for parsed_file in parsed_files:
        for statement_type, object_type, name_type in adapter.object_declarations:
            deadline.check()
            for statement in _descendants(parsed_file.tree, statement_type):
                name_segment = _statement_identifier(statement, name_type)
                if name_segment is not None:
                    builder.add_declaration(
                        object_type,
                        name_segment.raw,
                        parsed_file.path,
                    )
        adapter.collect_metadata(parsed_file, builder)

    for parsed_file in parsed_files:
        adapter.extract_flows(parsed_file, builder, linter)
        deadline.check()

    return LineageGraph(
        objects=list(builder.objects.values()),
        edges=list(builder.edges.values()),
        diagnostics=list(builder.diagnostics.values()),
    )


__all__ = ["analyze_repository"]
