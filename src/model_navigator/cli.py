import argparse
import sys
from pathlib import Path

from .dbt_graph import GraphLoadError, env_selection, load_manifest_graph
from .tui import ModelNavigatorApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="model-navigator",
        description="Navigate dbt lineage from the terminal.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help=(
            "Repo root, dbt project directory, dbt_project.yml, target directory, "
            "or manifest.json."
        ),
    )
    parser.add_argument(
        "--manifest-path",
        help="Use an explicit manifest.json file or directory containing it.",
    )
    parser.add_argument(
        "--select",
        help="Start on a specific node name, label, or dbt unique_id.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="How many visible columns to render to each side of the focus anchor in the current view.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        graph = load_manifest_graph(
            path=Path(args.path).expanduser() if args.path else None,
            manifest_path=(
                Path(args.manifest_path).expanduser() if args.manifest_path else None
            ),
        )
        selected = graph.resolve_selector(args.select or env_selection())
    except GraphLoadError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    app = ModelNavigatorApp(
        graph=graph,
        initial_selected=selected,
        initial_depth=max(args.depth, 0),
    )
    app.run()
