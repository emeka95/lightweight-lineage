"""Shared execution and report writing for lineage front ends."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightweight_lineage.analysis import analyze_repository
from lightweight_lineage.options import ScanOptions
from lightweight_lineage.report import render_html
from lightweight_lineage.scanner import ScanDeadline


@dataclass(frozen=True, slots=True)
class ScanRunResult:
    destination: Path
    output_format: str
    graph: dict[str, Any]


def run_scan(
    options: ScanOptions,
    *,
    output_format: str = "json",
    output: Path | None = None,
) -> ScanRunResult:
    """Analyze a repository and write its deterministic JSON or HTML report."""
    normalized_format = output_format.casefold()
    if normalized_format not in {"json", "html"}:
        raise ValueError("output_format must be 'json' or 'html'")

    deadline = ScanDeadline.start(options.timeout_seconds)
    graph = analyze_repository(options, deadline=deadline).to_dict()
    if normalized_format == "html":
        rendered = render_html(graph)
    else:
        rendered = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    deadline.check()

    if output is None:
        destination = (
            options.source.parent / "outputs" / f"lineage.{normalized_format}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
    else:
        destination = output
    destination.write_text(rendered, encoding="utf-8", newline="\n")
    return ScanRunResult(destination, normalized_format, graph)


__all__ = ["ScanRunResult", "run_scan"]
