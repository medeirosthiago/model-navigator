# Model Navigator

Terminal dbt lineage explorer built with Textual, Rich, and real dbt metadata.

## Installation

Install directly from GitHub:

```bash
uv tool install git+https://github.com/medeirosthiago/model-navigator.git
```

```bash
pipx install "git+https://github.com/medeirosthiago/model-navigator.git"
```

If you prefer plain pip:

```bash
pip install "git+https://github.com/medeirosthiago/model-navigator.git"
```

## Usage

```bash
uv run model-navigator
uv run model-navigator /path/to/repo --select my_model
uv run model-navigator --manifest /path/to/dbt/target/manifest.json
```

For scripts and editor integrations, inspect a model without opening the TUI:

```bash
uv run model-navigator inspect --manifest /path/to/dbt/target/manifest.json --select my_model --format json
```

The JSON output includes project metadata, the selected node, and direct upstream and downstream nodes with file paths and relation metadata.

## Neovim integration

This repository also includes a tiny Neovim plugin. It opens model-navigator in a terminal split and, when the current buffer is a dbt model, starts focused on the current file's model name. If `$DBT_MODEL_PATH` is set to a `manifest.json`, the plugin passes it as `--manifest`; otherwise it uses `$DBT_PROJECT_DIR`, `$MODEL_NAVIGATOR_PATH`, or nearest project discovery.

```lua
vim.pack.add({
  { src = 'file:///Users/mds/src/lab/model-navigator' },
})

require('model_navigator').setup({
  cmd = { 'uv', 'run', '--project', '/Users/mds/src/lab/model-navigator', '--', 'model-navigator' },
})
```

Commands and mappings:

- `:ModelNavigator` opens model-navigator for the current buffer model.
- `:ModelNavigator some_model` opens model-navigator focused on `some_model`.
- `<leader>mn` is mapped by default to open model-navigator.

Configure/disable the default mapping:

```lua
require('model_navigator').setup({
  keymaps = { open = '<leader>dn' },
  -- or: keymaps = false,
})
```

The app loads an existing `manifest.json`, starts in the selected-lineage view with node focus, and keeps the current TUI behavior: depth-limited navigation in either view, focused lineage connectors for the selected node, and arrow-key navigation across visible nodes. dbt `source()` dependencies are shown as source nodes with an amber border and label so they stand apart from model `ref()` dependencies.

For dense projects, you can switch between two graph views:

- `column window`: the original wide slice around the current anchor
- `selected lineage`: only the selected node's lineage, still filtered by the current depth window

Use `/` to open the search picker, filter models by name, and jump directly into a focused lineage view. Use `v` to toggle between the two graph views, with `selected lineage` as the default.

Press `Enter` to open the selected node's file in `$EDITOR`. Terminal editors such as `vim` take over the current terminal session and return you to the same graph state when you exit. GUI editors such as `zed` and `cursor` open without blanking the TUI, which keeps rendering in the integrated terminal underneath.

## Metadata Discovery

Discovery prefers explicit inputs before defaults:

1. `--manifest`
2. positional `path`
3. `$DBT_MODEL_PATH`
4. `$DBT_PROJECT_DIR`
5. current working directory

When starting from a directory, model-navigator looks in sensible dbt places first:

- the directory itself if it is a dbt project
- common dbt subdirectories such as `dbt/`, `analytics/`, `transform/`, and `transforms/`
- then a recursive downward search for `manifest.json` and `dbt_project.yml`

For project-local artifact lookup it prefers `$DBT_TARGET_PATH` when set, then the normal dbt default of `target/manifest.json` relative to `dbt_project.yml`.

If multiple manifests are found, the app stops and asks for `--manifest` so you can choose explicitly.

## Selection

Use `--select <model>` to focus a specific node at startup. Selectors match:

- dbt `unique_id`
- model or node name
- rendered label such as `source_name.table_name`

You can also set a default selection with `$MODEL_NAVIGATOR_SELECT`.

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `h` / `←` | Previous node |
| `l` / `→` | Next node |
| `k` / `↑` | Node above |
| `j` / `↓` | Node below |
| `u` | Cycle direct upstream relations |
| `n` | Cycle direct downstream relations |
| `/` | Search nodes |
| `Enter` | Open in editor |
| `f` | Toggle focus mode |
| `v` | Toggle view |
| `[` / `]` | Decrease / increase depth |
| `Ctrl-Q` | Quit |
