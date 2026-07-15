import json

from model_navigator.dbt_graph import load_manifest_graph


def test_load_manifest_graph_links_refs_and_sources(tmp_path):
    project_dir = tmp_path / "dbt"
    target_dir = project_dir / "target"
    target_dir.mkdir(parents=True)
    (project_dir / "dbt_project.yml").write_text("name: test_project\n", encoding="utf-8")

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "project_name": "test_project",
                    "dbt_version": "1.8.0",
                },
                "nodes": {
                    "model.test_project.orders": {
                        "resource_type": "model",
                        "name": "orders",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`mart`.`orders`",
                        "original_file_path": "models/orders.sql",
                        "depends_on": {
                            "nodes": [
                                "model.test_project.customers",
                                "source.test_project.app.users",
                            ],
                        },
                    },
                    "model.test_project.customers": {
                        "resource_type": "model",
                        "name": "customers",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`mart`.`customers`",
                        "original_file_path": "models/customers.sql",
                        "config": {"materialized": "ephemeral"},
                        "depends_on": {"nodes": []},
                    },
                },
                "sources": {
                    "source.test_project.app.users": {
                        "resource_type": "source",
                        "source_name": "app",
                        "name": "users",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`raw`.`users`",
                        "original_file_path": "models/sources.yml",
                        "depends_on": {"nodes": []},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    graph = load_manifest_graph(manifest_path=manifest_path)

    assert graph.nodes["source.test_project.app.users"].label == "users"
    assert (
        graph.nodes["source.test_project.app.users"].relation_name
        == "analytics.raw.users"
    )
    assert graph.nodes["source.test_project.app.users"].relation_project == "analytics"
    assert graph.nodes["source.test_project.app.users"].relation_dataset == "raw"
    assert graph.nodes["source.test_project.app.users"].relation_identifier == "users"
    assert graph.nodes["source.test_project.app.users"].resource_type == "source"
    assert (
        graph.nodes["model.test_project.customers"].materialized == "ephemeral"
    )
    assert set(graph.nodes["model.test_project.orders"].upstream) == {
        "model.test_project.customers",
        "source.test_project.app.users",
    }
    assert graph.nodes["source.test_project.app.users"].downstream == (
        "model.test_project.orders",
    )
    assert graph.resolve_selector("app.users") == "source.test_project.app.users"
    assert graph.resolve_selector("analytics.raw.users") == "source.test_project.app.users"
