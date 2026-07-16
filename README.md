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
  { src = 'file:///path/to/model-navigator' },
})

require('model_navigator').setup({
  cmd = { 'uv', 'run', '--project', '/path/to/model-navigator', '--', 'model-navigator' },
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

The app loads an existing `manifest.json` into a depth-limited lineage view with node focus. Navigate to another visible model and press `Space` to make it the lineage anchor. Use `Ctrl-O` to jump back through previous anchors and `Ctrl-I` to move forward again, as in Vim. Terminals encode `Ctrl-I` as `Tab`, so either key moves forward. dbt `source()` dependencies use an amber border, while ephemeral models use dashed borders so inline transformations stand apart from physical relations.

Use `/` to open the search picker, filter models by name, and jump directly into that model's lineage.

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
| `Space` | Focus selected model's lineage |
| `Ctrl-O` | Jump to previous lineage anchor |
| `Ctrl-I` / `Tab` | Jump to next lineage anchor |
| `Enter` | Open in editor |
| `f` | Toggle focus mode |
| `[` / `]` | Decrease / increase depth |
| `Ctrl-Q` | Quit |
