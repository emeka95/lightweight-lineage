from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lightweight_lineage.gui import build_scan_options


class GuiOptionsTests(unittest.TestCase):
    def test_builds_shared_scan_options_from_form_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            options = build_scan_options(
                f" {root} ",
                "45",
                "\nlegacy.orders = dbo.orders\n",
                "schema=sales\n",
            )

        self.assertEqual(options.source, root)
        self.assertEqual(options.timeout_seconds, 45)
        self.assertEqual(options.dialect, "tsql")
        self.assertEqual(
            [(mapping.alias, mapping.target) for mapping in options.mappings],
            [("legacy.orders", "dbo.orders")],
        )
        self.assertEqual(
            [(variable.name, variable.value) for variable in options.template_variables],
            [("schema", "sales")],
        )

    def test_builds_options_for_redshift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            options = build_scan_options(
                temporary_directory,
                "300",
                "",
                "",
                "Redshift",
            )

        self.assertEqual(options.dialect, "redshift")

    def test_reports_malformed_mapping_with_its_form_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "Mapping line 2: expected ALIAS=TARGET"):
                build_scan_options(
                    temporary_directory,
                    "300",
                    "\ninvalid mapping\n",
                    "",
                )

    def test_rejects_invalid_timeout_and_conflicting_template_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "whole number"):
                build_scan_options(temporary_directory, "1.5", "", "")
            with self.assertRaisesRegex(ValueError, "at least one"):
                build_scan_options(temporary_directory, "0", "", "")
            with self.assertRaisesRegex(ValueError, "conflicting values"):
                build_scan_options(
                    temporary_directory,
                    "300",
                    "",
                    "schema=dbo\nschema=other",
                )

    def test_rejects_a_file_as_the_source_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "not-a-directory.sql"
            source.write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not a directory"):
                build_scan_options(str(source), "300", "", "")


if __name__ == "__main__":
    unittest.main()
