# Model Navigator

Terminal dbt lineage explorer built with Textual, Rich, and real dbt metadata.

## Usage

```bash
uv run model-navigator
uv run model-navigator /path/to/repo --select my_model
uv run model-navigator --manifest-path /path/to/dbt/target/manifest.json
```

The app loads an existing `manifest.json`, starts in the selected-lineage view with node focus, and keeps the current TUI behavior: depth-limited navigation in either view, focused lineage connectors for the selected node, and arrow-key navigation across visible nodes.

For dense projects, you can switch between two graph views:

- `column window`: the original wide slice around the current anchor
- `selected lineage`: only the selected node's lineage, still filtered by the current depth window

Use `/` or `Ctrl+P` to open the command palette, fuzzy-search a model, and jump directly into its focused lineage view. Use `v` to toggle between the two graph views, with `selected lineage` as the default.

Press `Enter` to open the selected node's file in `$EDITOR`. Terminal editors such as `vim` take over the current terminal session and return you to the same graph state when you exit. GUI editors such as `zed` and `cursor` open without blanking the TUI, which keeps rendering in the integrated terminal underneath.

## Metadata Discovery

Discovery prefers explicit inputs before defaults:

1. `--manifest-path`
2. positional `path`
3. `$MODEL_NAVIGATOR_MANIFEST_PATH`
4. `$MODEL_NAVIGATOR_PATH`
5. `$DBT_PROJECT_DIR`
6. current working directory

When starting from a directory, model-navigator looks in sensible dbt places first:

- the directory itself if it is a dbt project
- common dbt subdirectories such as `dbt/`, `analytics/`, `transform/`, and `transforms/`
- then a recursive downward search for `manifest.json` and `dbt_project.yml`

For project-local artifact lookup it prefers `$DBT_TARGET_PATH` when set, then the normal dbt default of `target/manifest.json` relative to `dbt_project.yml`.

If multiple manifests are found, the app stops and asks for `--manifest-path` so you can choose explicitly.

## Selection

Use `--select <model>` to focus a specific node at startup. Selectors match:

- dbt `unique_id`
- model or node name
- rendered label such as `source_name.table_name`

You can also set a default selection with `$MODEL_NAVIGATOR_SELECT`.
