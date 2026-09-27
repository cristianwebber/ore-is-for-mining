-- Minimal emulation of Factorio's data stage, so the mod can be tested against
-- the real base game (and Space Age) prototypes from wube/factorio-data.
--
-- It is not a full game: graphics/sound metadata that the public data repo
-- does not ship is replaced by stubs, which is fine because the mod only
-- looks at types, names, flags, minable results and collision masks.

local harness = {}

local function read_version(dir)
  local f = io.open(dir .. "/info.json")
  if not f then return nil end
  local version = f:read("*a"):match('"version"%s*:%s*"([^"]+)"')
  f:close()
  return version
end

local function exists(path)
  local f = io.open(path)
  if f then f:close() return true end
  return false
end

-- `defines` is engine-provided; any path through it just needs to be a
-- distinct, indexable value.
local function auto(path)
  return setmetatable({}, {
    __index = function(t, k)
      local v = auto(path .. "." .. tostring(k))
      rawset(t, k, v)
      return v
    end,
    __tostring = function() return path end,
  })
end

local function permissive_stub()
  return setmetatable({}, { __index = function() return {} end })
end

-- opts:
--   factorio_data  path to a wube/factorio-data checkout
--   mod_dir        path to this mod
--   space_age      load elevated-rails, recycler, quality and space-age too
--   extra_mods     list of { name = ..., dir = ... } loaded after this mod
--   settings       startup setting overrides, { ["name"] = value }
-- Returns the populated `data` table.
function harness.load(opts)
  local fd = opts.factorio_data
  local mod_paths = { core = fd .. "/core", base = fd .. "/base" }
  local order = { "base" }
  if opts.space_age then
    for _, name in ipairs({ "elevated-rails", "recycler", "quality", "space-age" }) do
      if exists(fd .. "/" .. name .. "/info.json") then
        mod_paths[name] = fd .. "/" .. name
        table.insert(order, name)
      end
    end
  end
  mod_paths["ore-is-for-mining"] = opts.mod_dir
  table.insert(order, "ore-is-for-mining")
  for _, extra in ipairs(opts.extra_mods or {}) do
    mod_paths[extra.name] = extra.dir
    table.insert(order, extra.name)
  end

  mods = {}
  for _, name in ipairs(order) do
    mods[name] = read_version(mod_paths[name]) or "0.0.1"
  end
  feature_flags = {
    quality = opts.space_age, space_travel = opts.space_age, spoiling = opts.space_age,
    freezing = opts.space_age, segmented_units = opts.space_age,
    expansion_shaders = opts.space_age, rail_bridges = opts.space_age,
  }
  defines = auto("defines")
  log = function() end
  localised_print = function() end

  local current_mod
  local stubbed = {}
  local searchers = package.searchers or package.loaders
  table.insert(searchers, 2, function(name)
    local mod, rest = name:match("^__([%w%-_]+)__[/.](.+)$")
    local candidates = {}
    local function add(dir, rel)
      if not dir then return end
      rel = rel:gsub("%.lua$", "")
      table.insert(candidates, dir .. "/" .. rel:gsub("%.", "/") .. ".lua")
      table.insert(candidates, dir .. "/" .. rel .. ".lua")
    end
    if mod then
      add(mod_paths[mod], rest)
    else
      add(mod_paths[current_mod], name)
      add(fd .. "/core/lualib", name)
    end
    for _, path in ipairs(candidates) do
      if exists(path) then return assert(loadfile(path)) end
    end
    -- Sprite metadata ships with the game's graphics, not the public data repo.
    if name:find("^graphics[/.]") or name:find("[/.]graphics[/.]") then
      return function()
        return setmetatable({ width = 1, height = 1, shift = { 0, 0 }, line_length = 1,
          frames = 1, scale = 0.5, animation_speed = 1 }, { __index = function() return {} end })
      end
    end
    -- Other assets missing from the public repo (menu simulations, music).
    if mod and not rest:find("^prototypes") then
      table.insert(stubbed, name)
      return permissive_stub
    end
    return "\n\tno harness path for " .. name
  end)

  local builtin = { _G = true, package = true, string = true, table = true, math = true,
    io = true, os = true, coroutine = true, debug = true, bit32 = true }
  local function run(mod, file)
    local path = mod_paths[mod] .. "/" .. file
    if not exists(path) then return end
    current_mod = mod
    -- Factorio gives every mod its own require cache.
    for k in pairs(package.loaded) do
      if not builtin[k] then package.loaded[k] = nil end
    end
    dofile(path)
  end

  -- Settings stage.
  data = { raw = {}, extend = function(self, list)
    for _, p in ipairs(list) do
      self.raw[p.type] = self.raw[p.type] or {}
      self.raw[p.type][p.name] = p
    end
  end }
  for _, mod in ipairs(order) do run(mod, "settings.lua") end
  settings = { startup = {} }
  for _, kind in ipairs({ "bool-setting", "int-setting", "double-setting", "string-setting" }) do
    for name, s in pairs(data.raw[kind] or {}) do
      if s.setting_type == "startup" then settings.startup[name] = { value = s.default_value } end
    end
  end
  for name, value in pairs(opts.settings or {}) do
    assert(settings.startup[name], "unknown setting " .. name)
    settings.startup[name] = { value = value }
  end

  -- Data stage.
  current_mod = "core"
  dofile(fd .. "/core/lualib/dataloader.lua")
  -- Skip placeholder entries produced by stubbed asset modules.
  local real_extend = data.extend
  data.extend = function(self, list)
    local clean = {}
    for _, p in ipairs(list) do
      if type(p.type) == "string" and type(p.name) == "string" then table.insert(clean, p) end
    end
    if #clean > 0 then real_extend(self, clean) end
  end
  run("core", "data.lua")
  for _, file in ipairs({ "data.lua", "data-updates.lua", "data-final-fixes.lua" }) do
    for _, mod in ipairs(order) do run(mod, file) end
  end

  return data, stubbed
end

return harness
