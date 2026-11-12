from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from lightweight_lineage.analysis_core import GraphBuilder, Reference
from lightweight_lineage.analysis import analyze_repository
from lightweight_lineage.dialects import get_dialect_adapter
from lightweight_lineage.dialects.base import (
    DialectAdapter,
    ParseDiagnostic,
    ParseResult,
    ParsedFile,
)
from lightweight_lineage.dialects.redshift import RedshiftAdapter
from lightweight_lineage.dialects.tsql import TSqlAdapter
from lightweight_lineage.options import ScanOptions
from lightweight_lineage.scanner import ScanDeadline


@dataclass(frozen=True)
class _TextParsedFile:
    path: str
    content: str


class _TextAdapter(DialectAdapter):
    source_extensions: tuple[str, ...] = (".txt",)
    object_declarations: tuple[tuple[str, str, str], ...] = ()

    def parse(self, source: str, path: str) -> ParseResult:
        return ParseResult(
            _TextParsedFile(path, source),
            (ParseDiagnostic("info", "text_parser_used", "Parsed as text."),),
        )

    def collect_declarations(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        text_file = self._text_file(parsed_file)
        builder.add_declaration("table", "text.source", text_file.path)
        builder.add_declaration("table", "text.target", text_file.path)

    def extract_flows(
        self,
        parsed_file: ParsedFile,
        builder: GraphBuilder,
    ) -> None:
        text_file = self._text_file(parsed_file)
        if "source -> target" not in text_file.content:
            return
        source_id = builder.find_declared_object_id("text.source", "table")
        target_id = builder.find_declared_object_id("text.target", "table")
        source = builder.get_object(source_id) if source_id is not None else None
        target = builder.get_object(target_id) if target_id is not None else None
        if source is None or target is None:
            raise RuntimeError("Text adapter declarations were not collected.")
        builder.add_edge(
            source,
            target,
            "data_flow",
            "confirmed",
            text_file.path,
            1,
            1,
        )

    @staticmethod
    def _text_file(parsed_file: ParsedFile) -> _TextParsedFile:
        if not isinstance(parsed_file, _TextParsedFile):
            raise TypeError("Text adapter received an unsupported parsed-file type.")
        return parsed_file


class DialectAdapterTests(unittest.TestCase):
    def test_supported_dialects_return_adapters_with_valid_declarations(self) -> None:
        expected_adapters = {
            "tsql": TSqlAdapter,
            "redshift": RedshiftAdapter,
        }

        for dialect, adapter_type in expected_adapters.items():
            with self.subTest(dialect=dialect):
                adapter = get_dialect_adapter(dialect)
                self.assertIsInstance(adapter, adapter_type)
                self.assertEqual(adapter.source_extensions, (".sql",))
                self.assertTrue(adapter.object_declarations)
                self.assertEqual(
                    len(adapter.object_declarations),
                    len(set(adapter.object_declarations)),
                )
                for declaration in adapter.object_declarations:
                    self.assertEqual(len(declaration), 3)
                    self.assertTrue(all(declaration))

                parsed = adapter.parse("SELECT 1;", "valid.sql")
                self.assertIsNotNone(parsed.parsed_file)
                self.assertEqual(parsed.parsed_file.path, "valid.sql")
                self.assertEqual(parsed.diagnostics, ())

                invalid = adapter.parse(
                    "CREATE VIEW analytics.invalid AS SELECT id FROM ;",
                    "invalid.sql",
                )
                self.assertIsNone(invalid.parsed_file)
                self.assertTrue(invalid.diagnostics)
                self.assertEqual(
                    {diagnostic.code for diagnostic in invalid.diagnostics},
                    {"sql_parse_error"},
                )

    def test_unsupported_dialect_raises_value_error(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported SQL dialect: unknown",
        ):
            get_dialect_adapter("unknown")

    def test_graph_builder_exposes_adapter_operations_without_internal_state(self) -> None:
        builder = GraphBuilder((), ScanDeadline.start(30))
        procedure = builder.add_declaration(
            "stored_procedure",
            "warehouse.refresh",
            "procedures.sql",
        )
        self.assertIsNotNone(procedure)
        if procedure is None:
            self.fail("A permanent stored procedure declaration should be retained.")

        builder.add_synonym("warehouse.refresh_alias", "warehouse.refresh")
        builder.add_synonym("warehouse.refresh_alias", "warehouse.refresh")
        resolved = builder.resolve(
            Reference(
                "warehouse.refresh_alias",
                "caller.sql",
                1,
                1,
                "stored_procedure",
            )
        )

        self.assertEqual([item.node.id for item in resolved], [procedure.id])
        self.assertEqual(
            builder.find_declared_object_id(
                "warehouse.refresh",
                "stored_procedure",
            ),
            procedure.id,
        )
        self.assertIs(builder.get_object(procedure.id), procedure)
        self.assertEqual(
            {item.id for item in builder.to_graph().objects},
            {procedure.id},
        )

    def test_orchestrator_accepts_parser_neutral_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "flow.txt").write_text("source -> target", encoding="utf-8")
            (root / "ignored.sql").write_text("not parsed", encoding="utf-8")
            adapter = _TextAdapter()
            with patch(
                "lightweight_lineage.dialects.get_dialect_adapter",
                return_value=adapter,
            ):
                graph = analyze_repository(ScanOptions(source=root)).to_dict()

        self.assertEqual(
            {item["id"] for item in graph["objects"]},
            {"table:text.source", "table:text.target"},
        )
        self.assertEqual(
            {
                (edge["source"], edge["target"], edge["kind"])
                for edge in graph["edges"]
            },
            {("table:text.source", "table:text.target", "data_flow")},
        )
        self.assertEqual(
            [
                (item["severity"], item["code"], item["file"])
                for item in graph["diagnostics"]
            ],
            [("info", "text_parser_used", "flow.txt")],
        )


if __name__ == "__main__":
    unittest.main()
