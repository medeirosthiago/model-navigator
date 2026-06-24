if vim.g.loaded_model_navigator == 1 then
  return
end
vim.g.loaded_model_navigator = 1

if vim.g.model_navigator_auto_setup ~= false then
  require('model_navigator').setup()
end
