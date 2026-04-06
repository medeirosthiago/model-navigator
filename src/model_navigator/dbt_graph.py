import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

VISIBLE_NODE_TYPES = {
    "model",
    "seed",
    "snapshot",
}
VISIBLE_TOP_LEVEL_KEYS = (
    "sources",
    "exposures",
    "metrics",
    "semantic_models",
    "saved_queries",
)
RESOURCE_SELECTION_PRIORITY = {
    "model": 0,
    "seed": 1,
    "snapshot": 2,
    "source": 3,
    "exposure": 4,
    "metric": 5,
    "semantic_model": 6,
    "saved_query": 7,
}
PREFERRED_PROJECT_DIR_NAMES = (
    "dbt",
    "analytics",
    "transform",
    "transforms",
)
SKIP_DISCOVERY_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dbt_packages",
    "logs",
    "node_modules",
    "site-packages",
}
MANIFEST_PATH_ENV_VAR = "DBT_MODEL_PATH"
DISCOVERY_ROOT_ENV_VARS = (
    "MODEL_NAVIGATOR_PATH",
    "DBT_PROJECT_DIR",
)
SELECT_ENV_VAR = "MODEL_NAVIGATOR_SELECT"
DBT_TARGET_PATH_ENV_VAR = "DBT_TARGET_PATH"


class GraphLoadError(RuntimeError):
    """Raised when dbt metadata cannot be discovered or loaded."""


@dataclass(frozen=True, slots=True)
class GraphMetadata:
    project_dir: Path
    manifest_path: Path
    project_name: str
    dbt_version: str
    generated_at: str | None


@dataclass(frozen=True, slots=True)
class GraphNode:
    unique_id: str
    name: str
    label: str
    resource_type: str
    package_name: str
    file_path: Path | None
    upstream: tuple[str, ...]
    downstream: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManifestGraph:
    metadata: GraphMetadata
    nodes: dict[str, GraphNode]
    selector_index: dict[str, tuple[str, ...]]

    def resolve_selector(self, selector: str | None) -> str:
        if not selector:
            return self.default_selection()

        normalized = selector.strip()
        if not normalized:
            return self.default_selection()

        if normalized in self.nodes:
            return normalized

        matches = self.selector_index.get(normalized.casefold(), ())
        if not matches:
            raise GraphLoadError(f"No dbt node matched selector {selector!r}.")
        if len(matches) == 1:
            return matches[0]

        prioritized = sorted(
            matches,
            key=lambda node_id: (
                RESOURCE_SELECTION_PRIORITY.get(
                    self.nodes[node_id].resource_type,
                    99,
                ),
                self.nodes[node_id].label.casefold(),
                node_id.casefold(),
            ),
        )
        top_priority = RESOURCE_SELECTION_PRIORITY.get(
            self.nodes[prioritized[0]].resource_type,
            99,
        )
        top_matches = [
            node_id
            for node_id in prioritized
            if RESOURCE_SELECTION_PRIORITY.get(self.nodes[node_id].resource_type, 99)
            == top_priority
        ]
        if len(top_matches) == 1:
            return top_matches[0]

        choices = ", ".join(top_matches)
        raise GraphLoadError(f"Selector {selector!r} is ambiguous. Matches: {choices}.")

    def default_selection(self) -> str:
        models = [
            node_id
            for node_id, node in self.nodes.items()
            if node.resource_type == "model"
        ]
        pool = models or list(self.nodes)
        if not pool:
            raise GraphLoadError(
                "The manifest does not contain any supported lineage nodes."
            )

        ranked = sorted(
            pool,
            key=lambda node_id: (
                -(
                    len(self.nodes[node_id].upstream)
                    + len(self.nodes[node_id].downstream)
                ),
                self.nodes[node_id].label.casefold(),
                node_id.casefold(),
            ),
        )
        return ranked[0]


@dataclass(frozen=True, slots=True)
class ManifestLocation:
    project_dir: Path
    manifest_path: Path


def load_manifest_graph(
    path: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> ManifestGraph:
    location = discover_manifest_location(path=path, manifest_path=manifest_path)
    try:
        raw_manifest = json.loads(location.manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GraphLoadError(
            f"Manifest not found at {location.manifest_path}. Run dbt parse or dbt compile first."
        ) from error
    except json.JSONDecodeError as error:
        raise GraphLoadError(
            f"Manifest is not valid JSON: {location.manifest_path}"
        ) from error

    metadata = GraphMetadata(
        project_dir=location.project_dir,
        manifest_path=location.manifest_path,
        project_name=raw_manifest.get("metadata", {}).get(
            "project_name",
            location.project_dir.name,
        ),
        dbt_version=raw_manifest.get("metadata", {}).get("dbt_version", "unknown"),
        generated_at=raw_manifest.get("metadata", {}).get("generated_at"),
    )

    raw_nodes = _collect_visible_nodes(raw_manifest)
    if not raw_nodes:
        raise GraphLoadError(
            f"No supported dbt lineage nodes were found in {location.manifest_path}."
        )

    visible_ids = set(raw_nodes)
    upstream_map: dict[str, list[str]] = defaultdict(list)
    downstream_map: dict[str, list[str]] = defaultdict(list)
    for unique_id, node in raw_nodes.items():
        for parent_id in node.get("depends_on", {}).get("nodes", []):
            if parent_id not in visible_ids:
                continue
            upstream_map[unique_id].append(parent_id)
            downstream_map[parent_id].append(unique_id)

    nodes: dict[str, GraphNode] = {}
    selector_index: dict[str, set[str]] = defaultdict(set)
    for unique_id, node in raw_nodes.items():
        resource_type = node.get("resource_type", "unknown")
        name = node.get("name", unique_id)
        label = _build_label(node, resource_type, name)
        graph_node = GraphNode(
            unique_id=unique_id,
            name=name,
            label=label,
            resource_type=resource_type,
            package_name=node.get("package_name", metadata.project_name),
            file_path=_resolve_file_path(
                metadata.project_dir,
                node.get("original_file_path") or node.get("path"),
            ),
            upstream=tuple(
                sorted(
                    upstream_map.get(unique_id, []),
                    key=lambda item: _node_sort_key(item, raw_nodes),
                )
            ),
            downstream=tuple(
                sorted(
                    downstream_map.get(unique_id, []),
                    key=lambda item: _node_sort_key(item, raw_nodes),
                )
            ),
        )
        nodes[unique_id] = graph_node

        selector_index[unique_id.casefold()].add(unique_id)
        selector_index[name.casefold()].add(unique_id)
        selector_index[label.casefold()].add(unique_id)
        selector_index[f"{graph_node.package_name}.{name}".casefold()].add(unique_id)
        selector_index[f"{graph_node.package_name}.{label}".casefold()].add(unique_id)

    return ManifestGraph(
        metadata=metadata,
        nodes=nodes,
        selector_index={
            key: tuple(sorted(value)) for key, value in selector_index.items()
        },
    )


def discover_manifest_location(
    path: Path | str | None = None,
    manifest_path: Path | str | None = None,
) -> ManifestLocation:
    explicit_manifest = _expand_path(manifest_path)
    if explicit_manifest is not None:
        return _resolve_manifest_input(explicit_manifest)

    if path is not None:
        return _discover_from_root(_resolve_existing_path(Path(path).expanduser()))

    explicit_manifest = _expand_path(os.environ.get(MANIFEST_PATH_ENV_VAR))
    if explicit_manifest is not None:
        return _resolve_manifest_input(explicit_manifest)

    root = _resolve_discovery_root(path)
    return _discover_from_root(root)


def env_selection() -> str | None:
    value = os.environ.get(SELECT_ENV_VAR)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _collect_visible_nodes(raw_manifest: dict) -> dict[str, dict]:
    visible: dict[str, dict] = {}
    for unique_id, node in raw_manifest.get("nodes", {}).items():
        if node.get("resource_type") in VISIBLE_NODE_TYPES:
            visible[unique_id] = node
    for key in VISIBLE_TOP_LEVEL_KEYS:
        for unique_id, node in raw_manifest.get(key, {}).items():
            visible[unique_id] = node
    return visible


def _build_label(node: dict, resource_type: str, name: str) -> str:
    if resource_type == "source":
        source_name = node.get("source_name")
        if source_name:
            return f"{source_name}.{name}"
    return name


def _node_sort_key(node_id: str, raw_nodes: dict[str, dict]) -> tuple[str, str]:
    node = raw_nodes[node_id]
    name = node.get("name", node_id)
    return (
        _build_label(node, node.get("resource_type", "unknown"), name).casefold(),
        node_id.casefold(),
    )


def _resolve_discovery_root(path: Path | str | None) -> Path:
    if path is not None:
        return _resolve_existing_path(Path(path).expanduser())

    for variable in DISCOVERY_ROOT_ENV_VARS:
        value = _expand_path(os.environ.get(variable))
        if value is not None:
            return _resolve_existing_path(value)

    return Path.cwd().resolve()


def _resolve_manifest_input(path: Path) -> ManifestLocation:
    resolved = _resolve_existing_path(path)
    if resolved.is_file():
        if resolved.name != "manifest.json":
            raise GraphLoadError("Explicit manifest paths must point to manifest.json.")
        return _build_manifest_location(resolved)

    direct_manifest = resolved / "manifest.json"
    if direct_manifest.exists():
        return _build_manifest_location(direct_manifest.resolve())

    matches = _discover_manifest_matches(resolved)
    if not matches:
        raise GraphLoadError(f"Could not find manifest.json under {resolved}.")
    return _choose_single_match(
        matches,
        f"{resolved}",
    )


def _discover_from_root(root: Path) -> ManifestLocation:
    if root.is_file():
        if root.name == "manifest.json":
            return _build_manifest_location(root)
        if root.name == "dbt_project.yml":
            return _discover_from_project_dir(root.parent)
        raise GraphLoadError(
            f"Unsupported path {root}. Use a repo root, dbt project directory, target directory, dbt_project.yml, or manifest.json."
        )

    direct = _direct_manifest_match(root)
    if direct is not None:
        return direct

    preferred_matches: list[ManifestLocation] = []
    for name in PREFERRED_PROJECT_DIR_NAMES:
        candidate = root / name
        if candidate.is_dir():
            preferred_matches.extend(_discover_manifest_matches(candidate))
    if preferred_matches:
        return _choose_single_match(
            preferred_matches,
            f"preferred dbt directories under {root}",
        )

    discovered_matches = _discover_manifest_matches(root)
    if discovered_matches:
        return _choose_single_match(
            discovered_matches,
            f"{root}",
        )

    if (root / "dbt_project.yml").exists():
        searched = ", ".join(
            str(candidate) for candidate in _project_manifest_candidates(root)
        )
        raise GraphLoadError(
            f"Found dbt project at {root}, but no manifest.json. Looked for {searched}. Run dbt parse or dbt compile first."
        )

    raise GraphLoadError(
        "Could not find dbt metadata. Set --manifest-path, set "
        f"{MANIFEST_PATH_ENV_VAR}, or point model-navigator at a repo or dbt project directory."
    )


def _discover_from_project_dir(project_dir: Path) -> ManifestLocation:
    direct = _direct_manifest_match(project_dir)
    if direct is not None:
        return direct

    matches = _discover_manifest_matches(project_dir)
    if matches:
        return _choose_single_match(matches, f"{project_dir}")

    searched = ", ".join(
        str(candidate) for candidate in _project_manifest_candidates(project_dir)
    )
    raise GraphLoadError(
        f"Found dbt project at {project_dir}, but no manifest.json. Looked for {searched}. Run dbt parse or dbt compile first."
    )


def _direct_manifest_match(directory: Path) -> ManifestLocation | None:
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        return _build_manifest_location(manifest_path.resolve())

    if not (directory / "dbt_project.yml").exists():
        return None

    for candidate in _project_manifest_candidates(directory):
        if candidate.exists():
            return ManifestLocation(
                project_dir=directory.resolve(),
                manifest_path=candidate.resolve(),
            )
    return None


def _project_manifest_candidates(project_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    target_override = os.environ.get(DBT_TARGET_PATH_ENV_VAR)
    if target_override:
        target_path = Path(target_override).expanduser()
        if target_path.is_absolute():
            candidate = target_path
        else:
            candidate = project_dir / target_path
        if candidate.name != "manifest.json":
            candidate = candidate / "manifest.json"
        candidates.append(candidate.resolve())

    default_candidate = (project_dir / "target" / "manifest.json").resolve()
    if default_candidate not in candidates:
        candidates.append(default_candidate)
    return candidates


def _discover_manifest_matches(root: Path) -> list[ManifestLocation]:
    matches: dict[Path, ManifestLocation] = {}
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name for name in dir_names if name not in SKIP_DISCOVERY_DIRS
        )
        current_path = Path(current_root)

        if "dbt_project.yml" in file_names:
            for candidate in _project_manifest_candidates(current_path):
                if candidate.exists():
                    matches[candidate] = ManifestLocation(
                        project_dir=current_path.resolve(),
                        manifest_path=candidate.resolve(),
                    )
                    break

        if "manifest.json" in file_names:
            manifest_path = (current_path / "manifest.json").resolve()
            matches.setdefault(manifest_path, _build_manifest_location(manifest_path))

    return sorted(matches.values(), key=lambda match: str(match.manifest_path))


def _choose_single_match(
    matches: list[ManifestLocation],
    scope: str,
) -> ManifestLocation:
    unique_matches = sorted(
        {(match.project_dir, match.manifest_path) for match in matches},
        key=lambda item: str(item[1]),
    )
    if len(unique_matches) == 1:
        project_dir, manifest_path = unique_matches[0]
        return ManifestLocation(project_dir=project_dir, manifest_path=manifest_path)

    choices = "\n".join(f"- {manifest_path}" for _, manifest_path in unique_matches)
    raise GraphLoadError(
        f"Found multiple manifest.json files under {scope}:\n{choices}\n"
        "Pass --manifest-path or set DBT_MODEL_PATH to choose one."
    )


def _build_manifest_location(manifest_path: Path) -> ManifestLocation:
    project_dir = _nearest_project_dir(manifest_path.parent)
    if project_dir is None:
        if manifest_path.parent.name == "target":
            project_dir = manifest_path.parent.parent
        else:
            project_dir = manifest_path.parent
    return ManifestLocation(
        project_dir=project_dir.resolve(),
        manifest_path=manifest_path.resolve(),
    )


def _nearest_project_dir(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        if (current / "dbt_project.yml").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _resolve_file_path(
    project_dir: Path,
    raw_path: str | None,
) -> Path | None:
    if not raw_path:
        return None

    path = Path(raw_path)
    if path.is_absolute():
        return path

    candidates = [
        (project_dir / path).resolve(),
        (project_dir.parent / path).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _expand_path(value: Path | str | None) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser()
    stripped = value.strip()
    if not stripped:
        return None
    return Path(stripped).expanduser()


def _resolve_existing_path(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        raise GraphLoadError(f"Path does not exist: {resolved}")
    return resolved
