import json

from typer.testing import CliRunner

from model_navigator.cli import app


def test_inspect_json_outputs_direct_lineage(tmp_path):
    project_dir = tmp_path / "dbt"
    target_dir = project_dir / "target"
    models_dir = project_dir / "models"
    target_dir.mkdir(parents=True)
    models_dir.mkdir()
    (project_dir / "dbt_project.yml").write_text("name: test_project\n", encoding="utf-8")
    (models_dir / "orders.sql").write_text("select 1\n", encoding="utf-8")
    (models_dir / "customers.sql").write_text("select 1\n", encoding="utf-8")
    (models_dir / "dashboard.sql").write_text("select 1\n", encoding="utf-8")

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "project_name": "test_project",
                    "dbt_version": "1.8.0",
                    "generated_at": "2026-06-24T10:00:00Z",
                },
                "nodes": {
                    "model.test_project.orders": {
                        "resource_type": "model",
                        "name": "orders",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`mart`.`orders`",
                        "original_file_path": "models/orders.sql",
                        "depends_on": {"nodes": ["model.test_project.customers"]},
                    },
                    "model.test_project.customers": {
                        "resource_type": "model",
                        "name": "customers",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`mart`.`customers`",
                        "original_file_path": "models/customers.sql",
                        "depends_on": {"nodes": []},
                    },
                    "model.test_project.dashboard": {
                        "resource_type": "model",
                        "name": "dashboard",
                        "package_name": "test_project",
                        "relation_name": "`analytics`.`mart`.`dashboard`",
                        "original_file_path": "models/dashboard.sql",
                        "depends_on": {"nodes": ["model.test_project.orders"]},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "inspect",
            "--manifest",
            str(manifest_path),
            "--select",
            "orders",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["metadata"]["manifest_path"] == str(manifest_path)
    assert payload["selected"]["name"] == "orders"
    assert payload["selected"]["file_path"] == str(models_dir / "orders.sql")
    assert [node["name"] for node in payload["upstream"]] == ["customers"]
    assert [node["name"] for node in payload["downstream"]] == ["dashboard"]
    assert payload["upstream"][0]["relation_dataset"] == "mart"

