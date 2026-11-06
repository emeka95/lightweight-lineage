"""Command-line entry point for lineage analysis."""

from __future__ import annotations

import json
from pathlib import Path

import click

from lightweight_lineage.analysis import analyze_repository
from lightweight_lineage.options import (
    ExplicitMapping,
    ScanOptions,
    TemplateVariable,
)
from lightweight_lineage.report import render_html
from lightweight_lineage.scanner import (
    DEFAULT_TIMEOUT_SECONDS,
    ScanDeadline,
    ScanTimeoutError,
)


def _parse_mapping(value: str) -> ExplicitMapping:
    alias, separator, target = value.partition("=")
    alias = alias.strip()
    target = target.strip()
    if not separator or not alias or not target:
        raise click.BadParameter(
            "expected ALIAS=TARGET with both values non-empty",
            param_hint="--map",
        )
    return ExplicitMapping(alias, target)


def _parse_template_variable(value: str) -> TemplateVariable:
    name, separator, content = value.partition("=")
    name = name.strip()
    if not separator or not name.isidentifier():
        raise click.BadParameter(
            "expected a valid variable name and value in NAME=VALUE form",
            param_hint="--var",
        )
    if name.casefold() in {"ref", "source"}:
        raise click.BadParameter(
            "ref and source are reserved Jinja2 helper names",
            param_hint="--var",
        )
    return TemplateVariable(name, content)


@click.group()
def cli() -> None:
    """Scan repositories and generate data lineage."""


@cli.command()
@click.argument(
    "source",
    type=click.Path(path_type=Path, exists=True, file_okay=False, readable=True),
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Write to this file (default: SOURCE's parent/outputs/lineage.<format>).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(("json", "html"), case_sensitive=False),
    default="json",
    show_default=True,
    help="Output format: deterministic JSON or a self-contained HTML report.",
)
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=DEFAULT_TIMEOUT_SECONDS,
    show_default=True,
    help="Maximum time in seconds for the whole scan.",
)
@click.option(
    "--map",
    "mapping_values",
    multiple=True,
    metavar="ALIAS=TARGET",
    help="Collect an explicit object mapping; may be supplied more than once.",
)
@click.option(
    "--var",
    "template_values",
    multiple=True,
    metavar="NAME=VALUE",
    help="Provide a Jinja2 template variable; may be supplied more than once.",
)
def scan(
    source: Path,
    output: Path | None,
    output_format: str,
    timeout: int,
    mapping_values: tuple[str, ...],
    template_values: tuple[str, ...],
) -> None:
    """Analyze T-SQL files under SOURCE and emit lineage JSON or HTML."""
    variables = tuple(_parse_template_variable(value) for value in template_values)
    variable_names: dict[str, str] = {}
    for variable in variables:
        previous = variable_names.setdefault(variable.name, variable.value)
        if previous != variable.value:
            raise click.BadParameter(
                f"template variable {variable.name!r} has conflicting values",
                param_hint="--var",
            )
    options = ScanOptions(
        source=source,
        timeout_seconds=timeout,
        mappings=tuple(_parse_mapping(value) for value in mapping_values),
        template_variables=variables,
    )
    try:
        deadline = ScanDeadline.start(timeout)
        result = analyze_repository(options, deadline=deadline).to_dict()
        if output_format.casefold() == "html":
            rendered = render_html(result)
        else:
            rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        deadline.check()
        if output is None:
            destination = (
                source.parent / "outputs" / f"lineage.{output_format.casefold()}"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
        else:
            destination = output
        destination.write_text(rendered, encoding="utf-8", newline="\n")
        click.echo(
            f"Lineage {output_format.upper()} written to {destination}."
        )
    except ScanTimeoutError as error:
        raise click.ClickException(str(error)) from error
    except OSError as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
