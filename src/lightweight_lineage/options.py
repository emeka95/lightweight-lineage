"""Shared, validated options passed from front ends to the scan pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lightweight_lineage.scanner import DEFAULT_TIMEOUT_SECONDS


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
    mappings: tuple[ExplicitMapping, ...] = ()
    template_variables: tuple[TemplateVariable, ...] = ()

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
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


__all__ = ["ExplicitMapping", "ScanOptions", "TemplateVariable"]
