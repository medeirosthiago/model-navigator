"""CLI entrypoint for model-navigator."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from model_navigator.dbt_graph import GraphLoadError, env_selection, load_manifest_graph

app = typer.Typer(
    name="model-navigator",
    help="Model Navigator – Navigate dbt lineage from the terminal.",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Repo root, dbt project directory, dbt_project.yml, "
                "target directory, or manifest.json."
            ),
        ),
    ] = None,
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest-path", help="Use an explicit manifest.json file or directory"),
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
            manifest_path=manifest_path.expanduser() if manifest_path else None,
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


if __name__ == "__main__":
    app()
