"""Repository parsing and dialect-dispatched lineage analysis."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateError, TemplateRuntimeError

from lightweight_lineage.analysis_core import GraphBuilder
from lightweight_lineage.dialects.base import ParsedFile
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
    adapter = get_dialect_adapter(options.dialect)
    files = scan_repository(
        options.source,
        extensions=adapter.source_extensions,
        deadline=deadline,
    )
    builder = GraphBuilder(options.mappings, deadline)
    environment = Environment(undefined=StrictUndefined, autoescape=False)
    environment.globals.update({"ref": _jinja_ref, "source": _jinja_source})
    template_values = {
        variable.name: variable.value for variable in options.template_variables
    }
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
        parse_result = adapter.parse(rendered, path)
        deadline.check()
        for diagnostic in parse_result.diagnostics:
            builder.add_diagnostic(
                diagnostic.severity,
                diagnostic.code,
                path,
                diagnostic.message,
                diagnostic.line,
                diagnostic.column,
            )
        if parse_result.parsed_file is None:
            continue
        parsed_files.append(parse_result.parsed_file)

    for parsed_file in parsed_files:
        adapter.collect_declarations(parsed_file, builder)
        adapter.collect_metadata(parsed_file, builder)

    for parsed_file in parsed_files:
        adapter.extract_flows(parsed_file, builder)
        deadline.check()

    return builder.to_graph()


__all__ = ["analyze_repository"]
