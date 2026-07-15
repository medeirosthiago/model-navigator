"""CLI entrypoint for model-navigator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import click
import typer
from rich.console import Console
from typer.core import TyperGroup

from model_navigator.dbt_graph import GraphLoadError, env_selection, load_manifest_graph


class _DefaultGroup(TyperGroup):
    """Typer group that forwards unknown args to the default (run) command."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands:
            args = ["run", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="model-navigator",
    help="Model Navigator – Navigate dbt lineage from the terminal.",
    no_args_is_help=True,
    cls=_DefaultGroup,
)
console = Console()


def _node_payload(graph_node: Any) -> dict[str, str | None]:
    return {
        "unique_id": graph_node.unique_id,
        "name": graph_node.name,
        "label": graph_node.label,
        "resource_type": graph_node.resource_type,
        "materialized": graph_node.materialized,
        "package_name": graph_node.package_name,
        "file_path": str(graph_node.file_path) if graph_node.file_path else None,
        "relation_name": graph_node.relation_name,
        "relation_project": graph_node.relation_project,
        "relation_dataset": graph_node.relation_dataset,
        "relation_identifier": graph_node.relation_identifier,
    }


def _inspect_payload(
    path: Path | None,
    manifest: Path | None,
    select: str | None,
) -> dict[str, Any]:
    graph = load_manifest_graph(
        path=path.expanduser() if path else None,
        manifest_path=manifest.expanduser() if manifest else None,
    )
    selected = graph.resolve_selector(select or env_selection())
    selected_node = graph.nodes[selected]

    return {
        "metadata": {
            "project_dir": str(graph.metadata.project_dir),
            "manifest_path": str(graph.metadata.manifest_path),
            "project_name": graph.metadata.project_name,
            "dbt_version": graph.metadata.dbt_version,
            "generated_at": graph.metadata.generated_at,
        },
        "selected": _node_payload(selected_node),
        "upstream": [
            _node_payload(graph.nodes[node_id]) for node_id in selected_node.upstream
        ],
        "downstream": [
            _node_payload(graph.nodes[node_id]) for node_id in selected_node.downstream
        ],
    }


@app.command()
def run(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Repo root, dbt project directory, dbt_project.yml, "
                "target directory, or manifest.json."
            ),
        ),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to dbt manifest.json"),
    ] = None,
    select: Annotated[
        str | None,
        typer.Option("--select", "-s", help="Start on a specific node name, label, or unique_id"),
    ] = None,
    depth: Annotated[
        int,
        typer.Option("--depth", "-d", help="Visible columns to each side of the focus anchor"),
    ] = 2,
) -> None:
    """Navigate dbt lineage from the terminal."""
    from model_navigator.tui import ModelNavigatorApp

    try:
        graph = load_manifest_graph(
            path=path.expanduser() if path else None,
            manifest_path=manifest.expanduser() if manifest else None,
        )
        console.print(f"[dim]Project: {graph.metadata.project_name}[/dim]")
        console.print(
            f"[dim]Manifest: {graph.metadata.manifest_path} "
            f"({len(graph.nodes)} nodes)[/dim]"
        )

        selected = graph.resolve_selector(select or env_selection())
        console.print(f"[dim]Selected: {graph.nodes[selected].label}[/dim]")
    except GraphLoadError as error:
        console.print(f"[red]error:[/red] {error}")
        raise typer.Exit(code=2) from error

    tui = ModelNavigatorApp(
        graph=graph,
        initial_selected=selected,
        initial_depth=max(depth, 0),
    )
    tui.run()


@app.command()
def inspect(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Repo root, dbt project directory, dbt_project.yml, "
                "target directory, or manifest.json."
            ),
        ),
    ] = None,
    manifest: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to dbt manifest.json"),
    ] = None,
    select: Annotated[
        str | None,
        typer.Option("--select", "-s", help="Node name, label, or unique_id to inspect"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format. Currently only json is supported."),
    ] = "json",
) -> None:
    """Print direct upstream and downstream lineage for a dbt node."""
    if output_format != "json":
        console.print("[red]error:[/red] only --format json is supported")
        raise typer.Exit(code=2)

    try:
        payload = _inspect_payload(path=path, manifest=manifest, select=select)
    except GraphLoadError as error:
        console.print(f"[red]error:[/red] {error}")
        raise typer.Exit(code=2) from error

    typer.echo(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
