local M = {}

local DEFAULT_CMD = { 'model-navigator' }

local config = {
  cmd = DEFAULT_CMD,
  keymaps = { open = '<leader>mn' },
  path = nil,
  prefer_env_path = true,
  terminal = { split = 'belowright split', height = 0.45 },
}

local function copy_list(values)
  local out = {}
  for i, value in ipairs(values) do out[i] = value end
  return out
end

local function cmd_base()
  local configured = vim.g.model_navigator_cmd or config.cmd
  if type(configured) == 'table' then return copy_list(configured) end
  if type(configured) == 'string' and configured ~= '' then
    return vim.split(configured, ' ', { trimempty = true })
  end
  return copy_list(DEFAULT_CMD)
end

local function current_model_name()
  local name = vim.fn.expand('%:t:r')
  if name == '' then return nil end
  return name
end

local function current_file_dir()
  local path = vim.api.nvim_buf_get_name(0)
  if path ~= '' and vim.fn.filereadable(path) == 1 then
    return vim.fn.fnamemodify(path, ':p:h')
  end
  local alt = vim.fn.expand('%:p:h')
  if alt ~= '' then return alt end
  return vim.loop.cwd()
end

local function project_root()
  local file_dir = current_file_dir()

  -- Prefer the nearest dbt project. In monorepos, falling back to a broad git
  -- root makes model-navigator discover every manifest in the whole checkout.
  local dbt_project = vim.fs.find('dbt_project.yml', { upward = true, path = file_dir })[1]
  if dbt_project then
    return vim.fn.fnamemodify(dbt_project, ':h')
  end

  -- If the current file is under target/, use that dbt project instead of the
  -- repository root.
  local manifest = vim.fs.find('manifest.json', { upward = true, path = file_dir })[1]
  if manifest and vim.fn.fnamemodify(manifest, ':h:t') == 'target' then
    return vim.fn.fnamemodify(manifest, ':h:h')
  end

  local git = vim.fs.find('.git', { upward = true, path = file_dir })[1]
  if git then return vim.fn.fnamemodify(git, ':h:h') end
  return vim.loop.cwd()
end

local function ensure_server()
  if vim.v.servername and vim.v.servername ~= '' then return vim.v.servername end
  return vim.fn.serverstart()
end

local function editor_helper()
  local dir = vim.fn.stdpath('cache') .. '/model-navigator'
  vim.fn.mkdir(dir, 'p')
  local path = dir .. '/editor.sh'
  local lines = {
    '#!/bin/sh',
    "python3 - \"$NVIM_LISTEN_ADDRESS\" \"$1\" <<'PY'",
    'import subprocess',
    'import sys',
    'addr, file_path = sys.argv[1], sys.argv[2]',
    'expr = "execute(' .. "'" .. 'wincmd k | edit ' .. "'" .. ' . fnameescape(%r))" % file_path',
    'subprocess.run(["nvim", "--server", addr, "--remote-expr", expr], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)',
    'PY',
  }
  vim.fn.writefile(lines, path)
  vim.fn.setfperm(path, 'rwx------')
  return path
end

local function close_existing_terminals()
  local buffers = {}
  for _, win in ipairs(vim.api.nvim_list_wins()) do
    local buf = vim.api.nvim_win_get_buf(win)
    local ok, is_model_navigator = pcall(vim.api.nvim_buf_get_var, buf, 'model_navigator_terminal')
    if ok and is_model_navigator then
      buffers[buf] = true
      pcall(vim.api.nvim_win_close, win, true)
    end
  end
  for buf, _ in pairs(buffers) do
    if vim.api.nvim_buf_is_valid(buf) then
      pcall(vim.api.nvim_buf_delete, buf, { force = true })
    end
  end
end

local function open_terminal(command, cwd)
  close_existing_terminals()
  local term = config.terminal or {}
  vim.cmd(term.split or 'botright split')
  local term_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(term_buf)
  if term.height then
    local h = term.height
    if type(h) == 'number' and h > 0 and h < 1 then h = math.floor(vim.o.lines * h) end
    vim.cmd('resize ' .. tostring(h))
  end

  -- Textual redraws the full screen. A tiny scrollback prevents old frames from
  -- being kept above the live TUI in Neovim's terminal buffer, which otherwise
  -- looks like the app is rendered twice.
  vim.bo.scrollback = term.scrollback or 0

  local server = ensure_server()
  local env = {
    NVIM_LISTEN_ADDRESS = server,
    EDITOR = editor_helper(),
    VISUAL = editor_helper(),
  }
  vim.b.model_navigator_terminal = true
  vim.bo.buflisted = false
  vim.bo.bufhidden = 'wipe'
  vim.fn.termopen(command, { cwd = cwd, env = env })
  vim.schedule(function()
    if vim.api.nvim_win_is_valid(0) then
      pcall(vim.cmd, 'normal! G')
      pcall(vim.cmd, 'startinsert')
    end
  end)
end

local function valid_path(path)
  return path and path ~= '' and vim.fn.isdirectory(vim.fn.expand(path)) == 1
end

local function valid_file(path)
  return path and path ~= '' and vim.fn.filereadable(vim.fn.expand(path)) == 1
end

local function manifest_path(opts)
  opts = opts or {}
  local candidates = {}
  if opts.manifest and opts.manifest ~= '' then table.insert(candidates, opts.manifest) end
  if config.manifest and config.manifest ~= '' then table.insert(candidates, config.manifest) end
  if vim.env.DBT_MODEL_PATH and vim.env.DBT_MODEL_PATH ~= '' then table.insert(candidates, vim.env.DBT_MODEL_PATH) end
  if vim.env.MODEL_NAVIGATOR_MANIFEST and vim.env.MODEL_NAVIGATOR_MANIFEST ~= '' then table.insert(candidates, vim.env.MODEL_NAVIGATOR_MANIFEST) end
  for _, path in ipairs(candidates) do
    local expanded = vim.fn.expand(path)
    if valid_file(expanded) then return expanded end
  end
  return nil
end

local function navigator_path(opts)
  opts = opts or {}
  local candidates = {}
  if opts.path and opts.path ~= '' then table.insert(candidates, opts.path) end
  if config.prefer_env_path ~= false then
    if vim.env.DBT_PROJECT_DIR and vim.env.DBT_PROJECT_DIR ~= '' then table.insert(candidates, vim.env.DBT_PROJECT_DIR) end
    if vim.env.MODEL_NAVIGATOR_PATH and vim.env.MODEL_NAVIGATOR_PATH ~= '' then table.insert(candidates, vim.env.MODEL_NAVIGATOR_PATH) end
  end
  if config.path and config.path ~= '' then table.insert(candidates, config.path) end
  table.insert(candidates, project_root())

  for _, path in ipairs(candidates) do
    local expanded = vim.fn.expand(path)
    if valid_path(expanded) then return expanded end
  end

  vim.notify('model-navigator: no valid dbt project directory found', vim.log.levels.ERROR)
  return vim.loop.cwd()
end

function M.open(opts)
  opts = opts or {}
  local cmd = cmd_base()
  local manifest = manifest_path(opts)
  local root = nil
  if manifest then
    table.insert(cmd, '--manifest')
    table.insert(cmd, manifest)
    root = vim.fn.fnamemodify(manifest, ':h:h')
  else
    root = navigator_path(opts)
    if root and root ~= '' then
      table.insert(cmd, root)
    end
  end
  local select = opts.select or current_model_name()
  if select and select ~= '' then
    table.insert(cmd, '--select')
    table.insert(cmd, select)
  end
  open_terminal(cmd, root)
end

function M.setup(opts)
  opts = opts or {}
  config = vim.tbl_deep_extend('force', config, opts)
  vim.g.model_navigator_cmd = config.cmd
  vim.api.nvim_create_user_command('ModelNavigator', function(args)
    M.open({ select = args.args ~= '' and args.args or nil })
  end, { nargs = '?' })
  if config.keymaps ~= false then
    local maps = config.keymaps or {}
    vim.keymap.set('n', maps.open or '<leader>mn', function() M.open() end, { desc = 'Open model-navigator for current dbt model' })
  end
end

return M
