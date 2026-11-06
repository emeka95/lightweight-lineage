from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from click.testing import CliRunner

from lightweight_lineage.cli import cli


class ScanCommandTests(unittest.TestCase):
    def test_emits_lineage_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "source.sql").write_text(
                "CREATE TABLE source_table (id INT);",
                encoding="utf-8",
            )
            (root / "view.sql").write_text(
                "CREATE VIEW result_view AS SELECT id FROM source_table;",
                encoding="utf-8",
            )

            result = CliRunner().invoke(
                cli,
                ["scan", str(root)],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            output = root.parent / "outputs" / "lineage.json"
            self.assertTrue(output.is_file())
            self.assertIn("Lineage JSON written", result.output)
            graph = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(graph["run_status"], "completed")
            self.assertEqual(
                {item["id"] for item in graph["objects"]},
                {"table:source_table", "view:result_view"},
            )
            self.assertEqual(
                {
                    (edge["source"], edge["target"], edge["status"])
                    for edge in graph["edges"]
                },
                {("table:source_table", "view:result_view", "confirmed")},
            )

    def test_writes_lineage_json_to_requested_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "source.sql").write_text(
                "CREATE TABLE source_table (id INT);",
                encoding="utf-8",
            )
            output = Path(temporary_directory) / "scan.json"

            result = CliRunner().invoke(
                cli,
                ["scan", str(root), "--output", str(output)],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["run_status"],
                "completed",
            )

    def test_writes_self_contained_html_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "source.sql").write_text(
                "CREATE TABLE source_table (id INT);",
                encoding="utf-8",
            )
            output = Path(temporary_directory) / "lineage.html"

            result = CliRunner().invoke(
                cli,
                ["scan", str(root), "--format", "html", "--output", str(output)],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Lineage HTML written", result.output)
            report = output.read_text(encoding="utf-8")
            self.assertTrue(report.startswith("<!doctype html>"))
            self.assertIn("lineage-data", report)
            self.assertIn("source_table", report)

    def test_writes_default_html_to_outputs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "source.sql").write_text(
                "CREATE TABLE source_table (id INT);",
                encoding="utf-8",
            )

            result = CliRunner().invoke(
                cli,
                ["scan", str(root), "--format", "html"],
            )

            output = root.parent / "outputs" / "lineage.html"
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(output.is_file())
            self.assertIn("Lineage HTML written", result.output)
            self.assertTrue(
                output.read_text(encoding="utf-8").startswith("<!doctype html>")
            )

    def test_rejects_malformed_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = CliRunner().invoke(
                cli,
                ["scan", temporary_directory, "--map", "not-a-mapping"],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("ALIAS=TARGET", result.output)

    def test_passes_jinja_variable_values_to_templates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "template.sql").write_text(
                "CREATE TABLE {{ table_name }} (id INT);",
                encoding="utf-8",
            )

            result = CliRunner().invoke(
                cli,
                ["scan", str(root), "--var", "table_name=dbo.source"],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            graph = json.loads(
                (root.parent / "outputs" / "lineage.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                {item["id"] for item in graph["objects"]},
                {"table:dbo.source"},
            )

    def test_reports_undefined_template_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            root.mkdir()
            (root / "template.sql").write_text(
                "CREATE TABLE {{ missing_name }} (id INT);",
                encoding="utf-8",
            )

            result = CliRunner().invoke(cli, ["scan", str(root)])

            self.assertEqual(result.exit_code, 0, result.output)
            graph = json.loads(
                (root.parent / "outputs" / "lineage.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(graph["run_status"], "completed_with_errors")
            self.assertEqual(graph["diagnostics"][0]["code"], "template_error")

    def test_rejects_conflicting_template_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = CliRunner().invoke(
                cli,
                [
                    "scan",
                    temporary_directory,
                    "--var",
                    "schema=dbo",
                    "--var",
                    "schema=other",
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("conflicting values", result.output)

    def test_reports_invalid_scan_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "not-a-directory.sql"
            file_path.write_text("SELECT 1;", encoding="utf-8")
            result = CliRunner().invoke(cli, ["scan", str(file_path)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Error:", result.output)


if __name__ == "__main__":
    unittest.main()
