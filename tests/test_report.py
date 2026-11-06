from __future__ import annotations

import json
import re
import unittest
from typing import Any

from lightweight_lineage.report import (
    _compute_edge_ports,
    _compute_layout,
    _compute_merge_groups,
    render_html,
)


def _graph() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_status": "completed_with_warnings",
        "objects": [
            {"id": "table:a", "type": "table", "name": "a", "status": "declared"},
            {"id": "view:b", "type": "view", "name": "b", "status": "declared"},
            {"id": "view:c", "type": "view", "name": "c", "status": "declared"},
            {"id": "unknown:lonely", "type": "unknown", "name": "lonely", "status": "unknown"},
        ],
        "edges": [
            {
                "source": "table:a",
                "target": "view:b",
                "kind": "data_flow",
                "status": "confirmed",
                "evidence_file": "flow.sql",
                "line": 1,
            },
            {
                "source": "view:b",
                "target": "table:a",
                "kind": "data_flow",
                "status": "ambiguous",
                "evidence_file": "flow.sql",
                "line": 2,
            },
            {
                "source": "view:b",
                "target": "view:c",
                "kind": "data_flow",
                "status": "inferred",
                "evidence_file": "flow.sql",
                "line": 3,
            },
        ],
        "diagnostics": [
            {
                "severity": "warning",
                "code": "unresolved_reference",
                "file": "flow.sql",
                "line": 4,
                "message": "An object could not be resolved.",
            }
        ],
    }


class LineageReportTests(unittest.TestCase):
    def test_fan_in_edges_share_target_and_source_ports_remain_stable(self) -> None:
        incoming_edges = [
            {
                "source": f"table:{name}",
                "target": "view:result",
                "kind": "data_flow",
                "status": "confirmed",
            }
            for name in ("alpha", "bravo", "charlie", "delta")
        ]
        outgoing_edges = [
            {
                "source": "table:source",
                "target": f"view:{name}",
                "kind": "data_flow",
                "status": "confirmed",
            }
            for name in ("alpha", "bravo", "charlie", "delta")
        ]

        incoming_ports = _compute_edge_ports(incoming_edges)
        outgoing_ports = _compute_edge_ports(outgoing_edges)
        reordered_ports = _compute_edge_ports(list(reversed(outgoing_edges)))

        self.assertEqual(
            {port["target"] for port in incoming_ports},
            {34},
        )
        self.assertEqual(
            len({port["source"] for port in outgoing_ports}),
            len(outgoing_edges),
        )
        self.assertEqual(
            {
                edge["target"]: port["source"]
                for edge, port in zip(outgoing_edges, outgoing_ports)
            },
            {
                edge["target"]: port["source"]
                for edge, port in zip(reversed(outgoing_edges), reordered_ports)
            },
        )

    def test_incoming_edges_share_one_merge_group_per_target(self) -> None:
        edges = [
            {
                "source": f"table:{name}",
                "target": "view:result",
                "kind": "data_flow",
                "status": "confirmed",
            }
            for name in ("alpha", "bravo", "charlie", "delta")
        ]
        edges.append(
            {
                "source": "table:delta",
                "target": "view:other",
                "kind": "data_flow",
                "status": "confirmed",
            }
        )

        groups = _compute_merge_groups(
            edges,
            {"table:alpha", "table:bravo", "table:charlie", "table:delta", "view:result", "view:other"},
        )

        self.assertEqual(
            groups,
            [
                {"target": "view:other", "edgeIndices": [4]},
                {"target": "view:result", "edgeIndices": [0, 1, 2, 3]},
            ],
        )

    def test_layout_is_deterministic_and_collapses_cycles(self) -> None:
        graph = _graph()

        positions, width, height = _compute_layout(graph)
        repeated_positions, repeated_width, repeated_height = _compute_layout(graph)

        self.assertEqual(positions, repeated_positions)
        self.assertEqual((width, height), (repeated_width, repeated_height))
        self.assertEqual(positions["table:a"]["rank"], positions["view:b"]["rank"])
        self.assertGreater(positions["view:c"]["rank"], positions["view:b"]["rank"])
        self.assertEqual(positions["unknown:lonely"]["rank"], 0)
        self.assertEqual(set(positions), {item["id"] for item in graph["objects"]})

    def test_html_is_deterministic_offline_and_embeds_the_graph(self) -> None:
        graph = _graph()

        html = render_html(graph)
        repeated_html = render_html(graph)
        match = re.search(
            r'<script id="lineage-data" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )

        self.assertEqual(html, repeated_html)
        if match is None:
            self.fail("The report is missing its embedded graph payload.")
        payload = json.loads(match.group(1))
        self.assertEqual(payload["graph"], graph)
        self.assertEqual(set(payload["layout"]["positions"]), {
            item["id"] for item in graph["objects"]
        })
        self.assertNotIn('<script src=', html)
        self.assertNotIn('<link rel=', html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn(".empty-state[hidden] { display: none; }", html)
        self.assertIn('markerUnits: "userSpaceOnUse"', html)
        self.assertIn("const arrowClearance = 4", html)
        self.assertIn("function reachable", html)
        self.assertIn("Upstream dependencies", html)
        self.assertIn("Downstream dependencies", html)
        self.assertIn("for (const edge of outgoing.get(selectedId) || [])", html)

    def test_embedded_untrusted_text_cannot_close_the_data_script(self) -> None:
        graph = _graph()
        graph["objects"][0]["name"] = '</script><img src=x onerror="alert(1)">'

        html = render_html(graph)

        self.assertIn("\\u003c/script\\u003e", html)
        self.assertNotIn('</script><img src=x', html)
        self.assertNotIn('<img src=x onerror=', html)


if __name__ == "__main__":
    unittest.main()
