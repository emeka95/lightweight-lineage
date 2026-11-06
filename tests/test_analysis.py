from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lightweight_lineage.analysis import analyze_repository
from lightweight_lineage.options import ExplicitMapping, ScanOptions, TemplateVariable

REPOSITORY_ROOT = Path(__file__).parents[1]


class RepositoryAnalysisTests(unittest.TestCase):
    def analyze_sql(
        self,
        sql_files: dict[str, str],
        *,
        mappings: tuple[ExplicitMapping, ...] = (),
        template_variables: tuple[TemplateVariable, ...] = (),
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for relative_path, source in sql_files.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            return analyze_repository(
                ScanOptions(
                    source=root,
                    mappings=mappings,
                    template_variables=template_variables,
                )
            ).to_dict()

    def test_matches_expected_fixture_objects_and_edges(self) -> None:
        expected = json.loads(
            (REPOSITORY_ROOT / "fixtures/fix1/outputs/expected.json").read_text(
                encoding="utf-8"
            )
        )
        actual = analyze_repository(
            ScanOptions(source=REPOSITORY_ROOT / "fixtures/fix1/repo")
        ).to_dict()

        self.assertEqual(
            {item["id"] for item in actual["objects"]},
            {item["id"] for item in expected["objects"]},
        )
        expected_objects = {
            item["id"]: item for item in expected["objects"]
        }
        actual_objects = {item["id"]: item for item in actual["objects"]}
        for object_id, expected_object in expected_objects.items():
            for key, value in expected_object.items():
                self.assertEqual(actual_objects[object_id].get(key), value)
        edge_key = lambda edge: (
            edge["source"],
            edge["target"],
            edge["kind"],
            edge["status"],
            edge.get("via_procedure"),
        )
        self.assertEqual(
            {edge_key(edge) for edge in actual["edges"]},
            {edge_key(edge) for edge in expected["edges"]},
        )
        self.assertEqual(
            {
                (item["severity"], item["code"], item["file"])
                for item in actual["diagnostics"]
            },
            {
                (item["severity"], item["code"], item["file"])
                for item in expected["diagnostics"]
            },
        )
        self.assertEqual(actual["run_status"], expected["run_status"])

    def test_ctes_and_nested_queries_only_emit_permanent_sources(self) -> None:
        graph = self.analyze_sql(
            {
                "schema.sql": "CREATE TABLE dbo.a (id INT); CREATE TABLE dbo.b (id INT);",
                "view.sql": (
                    "CREATE VIEW dbo.result AS "
                    "WITH c AS (SELECT id FROM dbo.a), "
                    "d AS (SELECT id FROM c) "
                    "SELECT id FROM (SELECT id FROM d) nested "
                    "UNION SELECT id FROM dbo.b;"
                ),
            }
        )

        object_ids = {item["id"] for item in graph["objects"]}
        self.assertNotIn("unknown:c", object_ids)
        self.assertNotIn("unknown:d", object_ids)
        self.assertEqual(
            {
                (edge["source"], edge["target"])
                for edge in graph["edges"]
                if edge["kind"] == "data_flow"
            },
            {
                ("table:dbo.a", "view:dbo.result"),
                ("table:dbo.b", "view:dbo.result"),
            },
        )

    def test_explicit_mapping_overrides_sql_resolution_and_is_logged(self) -> None:
        graph = self.analyze_sql(
            {
                "tables.sql": (
                    "CREATE TABLE dbo.actual (id INT); "
                    "CREATE TABLE dbo.mapped (id INT);"
                ),
                "view.sql": "CREATE VIEW dbo.result AS SELECT id FROM dbo.actual;",
            },
            mappings=(ExplicitMapping("dbo.actual", "dbo.mapped"),),
        )

        self.assertIn(
            ("table:dbo.mapped", "view:dbo.result", "confirmed"),
            {
                (edge["source"], edge["target"], edge["status"])
                for edge in graph["edges"]
            },
        )
        self.assertIn(
            "mapping_override",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_conflicting_explicit_mappings_draw_ambiguous_candidate_edges(self) -> None:
        graph = self.analyze_sql(
            {
                "tables.sql": (
                    "CREATE TABLE dbo.first_candidate (id INT); "
                    "CREATE TABLE dbo.second_candidate (id INT);"
                ),
                "view.sql": "CREATE VIEW dbo.result AS SELECT id FROM source_alias;",
            },
            mappings=(
                ExplicitMapping("source_alias", "dbo.first_candidate"),
                ExplicitMapping("source_alias", "dbo.second_candidate"),
            ),
        )

        self.assertEqual(
            {
                edge["source"]
                for edge in graph["edges"]
                if edge["target"] == "view:dbo.result"
            },
            {"table:dbo.first_candidate", "table:dbo.second_candidate"},
        )
        self.assertEqual(
            {
                edge["status"]
                for edge in graph["edges"]
                if edge["target"] == "view:dbo.result"
            },
            {"ambiguous"},
        )
        self.assertIn(
            "ambiguous_mapping",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_single_qualified_candidate_is_inferred_and_logged(self) -> None:
        graph = self.analyze_sql(
            {
                "table.sql": "CREATE TABLE dbo.source (id INT);",
                "view.sql": "CREATE VIEW dbo.result AS SELECT id FROM source;",
            }
        )

        edge = next(edge for edge in graph["edges"] if edge["target"] == "view:dbo.result")
        self.assertEqual(edge["source"], "table:dbo.source")
        self.assertEqual(edge["status"], "inferred")
        self.assertIn(
            "inferred_reference",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_multiple_qualified_candidates_remain_unspecified(self) -> None:
        graph = self.analyze_sql(
            {
                "tables.sql": (
                    "CREATE TABLE dbo1.source (id INT); "
                    "CREATE TABLE dbo2.source (id INT);"
                ),
                "view.sql": "CREATE VIEW dbo.result AS SELECT id FROM source;",
            }
        )

        edge = next(edge for edge in graph["edges"] if edge["target"] == "view:dbo.result")
        self.assertEqual(edge["source"], "unknown:source")
        self.assertEqual(edge["status"], "unknown_source")
        self.assertIn(
            "inference_conflict",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_synonym_resolves_to_its_static_target(self) -> None:
        graph = self.analyze_sql(
            {
                "objects.sql": (
                    "CREATE TABLE dbo.real_table (id INT); "
                    "CREATE SYNONYM dbo.alias_table FOR dbo.real_table; "
                    "CREATE VIEW dbo.result AS SELECT id FROM dbo.alias_table;"
                )
            }
        )

        self.assertIn(
            ("table:dbo.real_table", "view:dbo.result"),
            {(edge["source"], edge["target"]) for edge in graph["edges"]},
        )
        self.assertNotIn(
            "unknown:dbo.alias_table",
            {item["id"] for item in graph["objects"]},
        )

    def test_jinja_ref_and_source_helpers_render_deterministically(self) -> None:
        graph = self.analyze_sql(
            {
                "source.sql": "CREATE TABLE dbo.real_source (id INT);",
                "views.sql": (
                    "CREATE VIEW dbo.ref_view AS "
                    "SELECT id FROM {{ ref('real_source') }}; "
                    "GO "
                    "CREATE VIEW dbo.source_view AS "
                    "SELECT id FROM {{ source('warehouse', 'real_source') }};"
                ),
            },
            mappings=(
                ExplicitMapping("warehouse.real_source", "dbo.real_source"),
            ),
        )

        edge_pairs = {
            (edge["source"], edge["target"])
            for edge in graph["edges"]
            if edge["kind"] == "data_flow"
        }
        self.assertIn(("table:dbo.real_source", "view:dbo.ref_view"), edge_pairs)
        self.assertIn(("table:dbo.real_source", "view:dbo.source_view"), edge_pairs)

    def test_conflicting_sql_declarations_remain_ambiguous(self) -> None:
        graph = self.analyze_sql(
            {
                "objects.sql": (
                    "CREATE TABLE dbo.conflict (id INT); GO "
                    "CREATE VIEW dbo.conflict AS SELECT id FROM dbo.source; GO "
                    "CREATE TABLE dbo.source (id INT); GO "
                    "CREATE VIEW dbo.result AS SELECT id FROM dbo.conflict;"
                )
            }
        )

        candidates = {
            edge["source"]
            for edge in graph["edges"]
            if edge["target"] == "view:dbo.result"
        }
        self.assertEqual(
            candidates,
            {"table:dbo.conflict", "view:dbo.conflict"},
        )
        self.assertIn(
            "ambiguous_sql_declaration",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_external_files_and_four_part_names_are_represented(self) -> None:
        graph = self.analyze_sql(
            {
                "sources.sql": (
                    "CREATE TABLE dbo.target (id INT); "
                    "BULK INSERT dbo.target FROM 'C:\\\\data\\\\input.csv'; "
                    "CREATE VIEW dbo.remote_view AS "
                    "SELECT id FROM [server].[database].[schema].[remote_table]; "
                    "CREATE VIEW dbo.file_view AS "
                    "SELECT * FROM OPENROWSET(BULK 'C:\\\\data\\\\view.csv', SINGLE_CLOB) AS f;"
                )
            }
        )

        object_ids = {item["id"] for item in graph["objects"]}
        self.assertIn("data_file:c:\\\\data\\\\input.csv", object_ids)
        self.assertIn(
            "external_connection:server",
            object_ids,
        )
        self.assertIn(
            "external_object:server.database.schema.remote_table",
            object_ids,
        )
        self.assertIn(
            ("data_file:c:\\\\data\\\\input.csv", "table:dbo.target"),
            {(edge["source"], edge["target"]) for edge in graph["edges"]},
        )
        self.assertIn(
            ("external_connection:server", "external_object:server.database.schema.remote_table", "connection"),
            {
                (edge["source"], edge["target"], edge["kind"])
                for edge in graph["edges"]
            },
        )
        self.assertIn(
            ("data_file:c:\\\\data\\\\view.csv", "view:dbo.file_view"),
            {(edge["source"], edge["target"]) for edge in graph["edges"]},
        )

    def test_parse_errors_are_reported_without_hiding_other_files(self) -> None:
        graph = self.analyze_sql(
            {
                "good.sql": "CREATE TABLE dbo.good (id INT);",
                "bad.sql": "CREATE VIEW dbo.bad AS SELECT FROM ;",
            }
        )

        self.assertIn("table:dbo.good", {item["id"] for item in graph["objects"]})
        self.assertNotIn("view:dbo.bad", {item["id"] for item in graph["objects"]})
        self.assertIn(
            "sql_parse_error",
            {diagnostic["code"] for diagnostic in graph["diagnostics"]},
        )

    def test_static_procedure_calls_are_recorded_but_dynamic_sql_is_not_parsed(self) -> None:
        graph = self.analyze_sql(
            {
                "procedures.sql": (
                    "CREATE PROCEDURE dbo.caller AS BEGIN "
                    "EXEC dbo.called; "
                    "EXEC(N'SELECT * FROM dbo.hidden'); "
                    "END; GO "
                    "CREATE PROCEDURE dbo.called AS BEGIN SELECT 1; END;"
                )
            }
        )

        self.assertIn(
            (
                "procedure:dbo.caller",
                "procedure:dbo.called",
                "procedure_call",
            ),
            {
                (edge["source"], edge["target"], edge["kind"])
                for edge in graph["edges"]
            },
        )
        self.assertNotIn(
            "unknown:dbo.hidden",
            {item["id"] for item in graph["objects"]},
        )

    def test_update_merge_and_select_into_extract_data_flow(self) -> None:
        graph = self.analyze_sql(
            {
                "dml.sql": (
                    "CREATE TABLE dbo.src (id INT); "
                    "CREATE TABLE dbo.dst (id INT); "
                    "UPDATE d SET id=s.id FROM dbo.dst d "
                    "JOIN dbo.src s ON d.id=s.id; "
                    "MERGE dbo.dst AS t USING dbo.src AS s ON t.id=s.id "
                    "WHEN MATCHED THEN UPDATE SET id=s.id; "
                    "SELECT id INTO dbo.copy FROM dbo.src;"
                )
            }
        )

        edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
        self.assertIn(("table:dbo.src", "table:dbo.dst"), edges)
        self.assertIn(("table:dbo.src", "table:dbo.copy"), edges)
        self.assertIn("table:dbo.copy", {item["id"] for item in graph["objects"]})


if __name__ == "__main__":
    unittest.main()
