from model_navigator.dbt_graph import GraphNode
from model_navigator.lineage import lineage_columns, lineage_nodes_with_depth


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


def test_lineage_nodes_with_depth_uses_dependency_hops():
    graph = {
        "source": _node("source", downstream=("prep",)),
        "prep": _node(
            "prep",
            upstream=("source",),
            downstream=("campaign", "device", "rebrandly"),
        ),
        "campaign": _node("campaign", upstream=("prep",), downstream=("rebrandly",)),
        "device": _node("device", upstream=("prep",), downstream=("rebrandly",)),
        "rebrandly": _node(
            "rebrandly",
            upstream=("campaign", "device", "prep"),
            downstream=("dashboard",),
        ),
        "dashboard": _node("dashboard", upstream=("other_parent", "rebrandly")),
        "other_parent": _node("other_parent", downstream=("dashboard",)),
    }

    assert lineage_columns(graph, "rebrandly") == {
        "source": -3,
        "prep": -2,
        "campaign": -1,
        "device": -1,
        "rebrandly": 0,
        "dashboard": 1,
    }

    columns = lineage_columns(graph, "rebrandly")
    for child, column in columns.items():
        for parent in graph[child].upstream:
            if parent in columns:
                assert columns[parent] < column

    assert lineage_nodes_with_depth(graph, "rebrandly", 1) == {
        "campaign",
        "device",
        "prep",
        "rebrandly",
        "dashboard",
    }
    assert lineage_nodes_with_depth(graph, "rebrandly", 2) == {
        "source",
        "prep",
        "campaign",
        "device",
        "rebrandly",
        "dashboard",
    }
