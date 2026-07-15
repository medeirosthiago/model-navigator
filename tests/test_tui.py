import asyncio

from model_navigator.dbt_graph import GraphMetadata, GraphNode, ManifestGraph
from model_navigator.tui import LineageGraph, ModelNavigatorApp


def _node(
    name: str,
    upstream: tuple[str, ...] = (),
    downstream: tuple[str, ...] = (),
) -> GraphNode:
    return GraphNode(
        unique_id=name,
        name=name,
        label=name,
        relation_name=None,
        relation_project=None,
        relation_dataset=None,
        relation_identifier=None,
        resource_type="model",
        materialized="table",
        package_name="test_project",
        file_path=None,
        upstream=upstream,
        downstream=downstream,
    )


def test_lineage_anchor_history(tmp_path):
    graph = ManifestGraph(
        metadata=GraphMetadata(
            project_dir=tmp_path,
            manifest_path=tmp_path / "manifest.json",
            project_name="test_project",
            dbt_version="1.8.0",
            generated_at=None,
        ),
        nodes={
            "a": _node("a", downstream=("b",)),
            "b": _node("b", upstream=("a",), downstream=("c",)),
            "c": _node("c", upstream=("b",)),
        },
        selector_index={},
    )

    async def run() -> None:
        app = ModelNavigatorApp(graph, "a", 2)
        async with app.run_test() as pilot:
            widget = app.query_one(LineageGraph)

            widget.selected = "b"
            await pilot.press("space")
            widget.selected = "c"
            await pilot.press("space")

            await pilot.press("ctrl+o")
            assert (widget.selected, widget.lineage_anchor) == ("b", "b")
            await pilot.press("ctrl+o")
            assert (widget.selected, widget.lineage_anchor) == ("a", "a")
            await pilot.press("ctrl+i")
            assert (widget.selected, widget.lineage_anchor) == ("b", "b")

    asyncio.run(run())
