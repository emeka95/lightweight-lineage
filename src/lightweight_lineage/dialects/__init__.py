"""SQL dialect adapters for lineage extraction."""

from __future__ import annotations

from lightweight_lineage.dialects.base import DialectAdapter


def get_dialect_adapter(dialect: str) -> DialectAdapter:
    """Return the adapter registered for a validated SQL dialect."""
    if dialect == "tsql":
        from lightweight_lineage.dialects.tsql import TSqlAdapter

        return TSqlAdapter()
    if dialect == "redshift":
        from lightweight_lineage.dialects.redshift import RedshiftAdapter

        return RedshiftAdapter()
    raise ValueError(f"Unsupported SQL dialect: {dialect}")


__all__ = ["DialectAdapter", "get_dialect_adapter"]
