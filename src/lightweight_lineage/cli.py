"""Command-line entry point for lineage analysis."""

from __future__ import annotations

from pathlib import Path

import click

from lightweight_lineage.options import (
    ExplicitMapping,
    ScanOptions,
    TemplateVariable,
    parse_mapping,
    parse_template_variable,
)
from lightweight_lineage.runner import run_scan
from lightweight_lineage.scanner import (
    DEFAULT_TIMEOUT_SECONDS,
    ScanTimeoutError,
)


def _parse_mapping(value: str) -> ExplicitMapping:
    try:
        return parse_mapping(value)
    except ValueError as error:
        raise click.BadParameter(str(error), param_hint="--map") from error


def _parse_template_variable(value: str) -> TemplateVariable:
    try:
        return parse_template_variable(value)
    except ValueError as error:
        raise click.BadParameter(str(error), param_hint="--var") from error


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
    "--dialect",
    type=click.Choice(("tsql", "redshift"), case_sensitive=False),
    default="tsql",
    show_default=True,
    help="SQL dialect used to parse source files.",
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
    dialect: str,
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
        dialect=dialect.casefold(),
        mappings=tuple(_parse_mapping(value) for value in mapping_values),
        template_variables=variables,
    )
    try:
        result = run_scan(options, output_format=output_format, output=output)
        click.echo(
            f"Lineage {result.output_format.upper()} written to {result.destination}."
        )
    except ScanTimeoutError as error:
        raise click.ClickException(str(error)) from error
    except OSError as error:
        raise click.ClickException(str(error)) from error


@cli.command()
@click.option(
    "--source",
    type=click.Path(path_type=Path, exists=True, file_okay=False, readable=True),
    help="Preselect a repository directory in the GUI.",
)
def gui(source: Path | None) -> None:
    """Open the offline desktop interface."""
    try:
        from lightweight_lineage.gui import GuiUnavailableError, launch_gui
    except ImportError as error:
        raise click.ClickException(
            "The desktop interface requires Python with Tk support."
        ) from error

    try:
        launch_gui(source)
    except GuiUnavailableError as error:
        raise click.ClickException(str(error)) from error


if __name__ == "__main__":
    cli()


__all__ = ["cli"]
