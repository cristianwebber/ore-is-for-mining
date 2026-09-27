local collision_mask_util = require("collision-mask-util")
local default_masks = require("collision-mask-defaults")

local LAYER = "opr_resource"
local startup = settings.startup

-- Entity types that may always be built on resource patches. Matching by type
-- means modded drills, belts, loaders, inserters, chests, beacons, poles and pipes are allowed
-- automatically.
local allowed_types = {
  ["mining-drill"] = true, -- includes pumpjacks
  ["transport-belt"] = true,
  ["underground-belt"] = true,
  ["linked-belt"] = true, -- used by modded underground-belt variants
  ["loader"] = true,
  ["loader-1x1"] = true,
  ["inserter"] = true,
  ["container"] = true, -- wooden, iron and steel chests
  ["logistic-container"] = true, -- logistic chests
  ["beacon"] = true,
  ["electric-pole"] = true,
  ["pipe"] = true,
  ["pipe-to-ground"] = true,
}

if startup["opr-allow-rails"].value then
  for _, type in pairs({
    "straight-rail", "half-diagonal-rail", "curved-rail-a", "curved-rail-b",
    "legacy-straight-rail", "legacy-curved-rail", "rail-ramp", "rail-support",
    "rail-signal", "rail-chain-signal", "train-stop",
  }) do
    allowed_types[type] = true
  end
end

if startup["opr-allow-splitters"].value then
  allowed_types["splitter"] = true
  allowed_types["lane-splitter"] = true
end

-- Types that are never restricted: things that move around the map (a car or
-- train colliding with ore would get stuck), elevated rails that pass over
-- the ground, and ghosts/proxies whose placement is checked via their target.
local ignored_types = {
  ["resource"] = true,
  ["character"] = true,
  ["car"] = true,
  ["spider-vehicle"] = true,
  ["spider-leg"] = true,
  ["spider-unit"] = true,
  ["unit"] = true,
  ["segmented-unit"] = true,
  ["locomotive"] = true,
  ["cargo-wagon"] = true,
  ["fluid-wagon"] = true,
  ["artillery-wagon"] = true,
  ["infinity-cargo-wagon"] = true,
  ["elevated-straight-rail"] = true,
  ["elevated-half-diagonal-rail"] = true,
  ["elevated-curved-rail-a"] = true,
  ["elevated-curved-rail-b"] = true,
  ["entity-ghost"] = true,
  ["tile-ghost"] = true,
  ["item-request-proxy"] = true,
}

local api = ore_is_for_mining
for type in pairs(api.allowed_types) do
  allowed_types[type] = true
end

local allowed_names = {}
for name in pairs(api.allowed_entities) do
  allowed_names[name] = true
end
for name in string.gmatch(startup["opr-extra-allowed-entities"].value, "[^,%s]+") do
  allowed_names[name] = true
end

local function has_flag(prototype, flag)
  for _, f in pairs(prototype.flags or {}) do
    if f == flag then return true end
  end
  return false
end

local function is_fluid_resource(resource)
  local minable = resource.minable
  if not minable then return false end
  for _, result in pairs(minable.results or {}) do
    if result.type == "fluid" then return true end
  end
  return false
end

local function add_layer(prototype)
  local mask = table.deepcopy(collision_mask_util.get_mask(prototype))
  mask.layers[LAYER] = true
  prototype.collision_mask = mask
end

-- Mark resource patches.
local include_fluids = startup["opr-include-fluid-resources"].value
for name, resource in pairs(data.raw["resource"] or {}) do
  if not api.ignored_resources[name]
    and (include_fluids or not is_fluid_resource(resource))
  then
    add_layer(resource)
  end
end

-- Mark every player-buildable entity that is not allowed on resources,
-- including entities from other mods.
for type in pairs(default_masks) do
  if not string.find(type, "/", 1, true)
    and not ignored_types[type]
    and data.raw[type]
  then
    for name, prototype in pairs(data.raw[type]) do
      local blocked = api.blocked_entities[name]
        or (not allowed_types[type]
          and not allowed_names[name]
          and has_flag(prototype, "player-creation"))
      if blocked then
        add_layer(prototype)
      end
    end
  end
end
