from __future__ import annotations

import unittest

from lightweight_lineage.analysis_core import GraphBuilder, Reference
from lightweight_lineage.dialects import get_dialect_adapter
from lightweight_lineage.dialects.redshift import RedshiftAdapter
from lightweight_lineage.dialects.tsql import TSqlAdapter
from lightweight_lineage.scanner import ScanDeadline


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
                self.assertTrue(adapter.object_declarations)
                self.assertEqual(
                    len(adapter.object_declarations),
                    len(set(adapter.object_declarations)),
                )
                for declaration in adapter.object_declarations:
                    self.assertEqual(len(declaration), 3)
                    self.assertTrue(all(declaration))

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


if __name__ == "__main__":
    unittest.main()
