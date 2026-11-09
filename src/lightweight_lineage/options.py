"""Shared, validated options passed from front ends to the scan pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lightweight_lineage.scanner import DEFAULT_TIMEOUT_SECONDS

SqlDialect = Literal["tsql", "redshift"]


@dataclass(frozen=True, slots=True)
class ExplicitMapping:
    alias: str
    target: str


@dataclass(frozen=True, slots=True)
class TemplateVariable:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class ScanOptions:
    source: Path
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    dialect: SqlDialect = "tsql"
    mappings: tuple[ExplicitMapping, ...] = ()
    template_variables: tuple[TemplateVariable, ...] = ()

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.dialect not in {"tsql", "redshift"}:
            raise ValueError("dialect must be 'tsql' or 'redshift'")
        if any(
            not mapping.alias.strip() or not mapping.target.strip()
            for mapping in self.mappings
        ):
            raise ValueError("mapping aliases and targets must be non-empty")
        if any(not variable.name.strip() for variable in self.template_variables):
            raise ValueError("template variable names must be non-empty")
        if any(
            variable.name.casefold() in {"ref", "source"}
            for variable in self.template_variables
        ):
            raise ValueError("ref and source are reserved Jinja2 helper names")
        variable_values: dict[str, str] = {}
        for variable in self.template_variables:
            previous = variable_values.setdefault(variable.name, variable.value)
            if previous != variable.value:
                raise ValueError(
                    f"template variable {variable.name!r} has conflicting values"
                )


def parse_mapping(value: str) -> ExplicitMapping:
    alias, separator, target = value.partition("=")
    alias = alias.strip()
    target = target.strip()
    if not separator or not alias or not target:
        raise ValueError("expected ALIAS=TARGET with both values non-empty")
    return ExplicitMapping(alias, target)


def parse_template_variable(value: str) -> TemplateVariable:
    name, separator, content = value.partition("=")
    name = name.strip()
    if not separator or not name.isidentifier():
        raise ValueError("expected a valid variable name and value in NAME=VALUE form")
    if name.casefold() in {"ref", "source"}:
        raise ValueError("ref and source are reserved Jinja2 helper names")
    return TemplateVariable(name, content)


__all__ = [
    "ExplicitMapping",
    "ScanOptions",
    "SqlDialect",
    "TemplateVariable",
    "parse_mapping",
    "parse_template_variable",
]
