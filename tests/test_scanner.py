from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightweight_lineage.scanner import ScanTimeoutError, scan_repository


class ScanRepositoryTests(unittest.TestCase):
    def test_discovers_sql_recursively_in_case_insensitive_sorted_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "z.sql").write_text("SELECT 1;", encoding="utf-8")
            (root / "A.SQL").write_text("SELECT 1;", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "b.sql").write_text("SELECT 1;", encoding="utf-8")
            (root / "ignored.sql.j2").write_text("SELECT 1;", encoding="utf-8")
            (root / "notes.txt").write_text("not SQL", encoding="utf-8")

            self.assertEqual(
                scan_repository(root),
                ("A.SQL", "nested/b.sql", "z.sql"),
            )

    def test_discovers_only_configured_extensions_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source.TXT").write_text("text", encoding="utf-8")
            (root / "query.sql").write_text("SELECT 1;", encoding="utf-8")
            (root / "notes.txt").write_text("text", encoding="utf-8")

            self.assertEqual(
                scan_repository(root, extensions=(".txt",)),
                ("notes.txt", "source.TXT"),
            )

    def test_discovers_thousands_of_files_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for index in range(1200):
                directory = root / f"group_{index % 12:02}"
                directory.mkdir(exist_ok=True)
                (directory / f"model_{index:04}.sql").write_text(
                    "SELECT 1;",
                    encoding="utf-8",
                )

            first_scan = scan_repository(root)
            second_scan = scan_repository(root)

            self.assertEqual(len(first_scan), 1200)
            self.assertEqual(first_scan, second_scan)
            self.assertEqual(first_scan, tuple(sorted(first_scan, key=str.casefold)))

    def test_raises_instead_of_returning_partial_results_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source.sql").write_text("SELECT 1;", encoding="utf-8")
            with patch(
                "lightweight_lineage.scanner.time.monotonic",
                side_effect=(0.0, 2.0),
            ):
                with self.assertRaises(ScanTimeoutError):
                    scan_repository(root, timeout_seconds=1)

    def test_rejects_non_positive_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "greater than zero"):
                scan_repository(temporary_directory, timeout_seconds=0)

    def test_rejects_invalid_source_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            for extensions in ((), ("sql",), (".",)):
                with self.subTest(extensions=extensions):
                    with self.assertRaisesRegex(ValueError, "suffixes"):
                        scan_repository(
                            temporary_directory,
                            extensions=extensions,
                        )

    def test_rejects_a_file_as_the_scan_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "source.sql"
            file_path.write_text("SELECT 1;", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                scan_repository(file_path)


if __name__ == "__main__":
    unittest.main()
