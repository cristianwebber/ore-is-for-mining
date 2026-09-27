-- Runs one test scenario in a fresh Lua process.
-- usage: lua tests/scenario.lua <factorio-data dir> <scenario name>
local fd, scenario_name = arg[1], arg[2]
local root = arg[0]:match("^(.*)/tests/scenario%.lua$") or "."
package.path = root .. "/tests/?.lua;" .. package.path

local harness = require("harness")

local LAYER = "opr_resource"

local scenarios = {}

-- Entity names every scenario can rely on.
local base_allowed = {
  "burner-mining-drill", "electric-mining-drill", "pumpjack",
  "transport-belt", "fast-transport-belt", "express-transport-belt",
  "underground-belt", "express-underground-belt",
  "loader", "fast-loader", "express-loader", "beacon",
  "burner-inserter", "inserter", "long-handed-inserter", "fast-inserter", "bulk-inserter",
  "wooden-chest", "iron-chest", "steel-chest", "passive-provider-chest", "active-provider-chest",
  "storage-chest", "buffer-chest", "requester-chest",
  "small-electric-pole", "medium-electric-pole", "big-electric-pole", "substation",
  "pipe", "pipe-to-ground",
}
local base_blocked = {
  "assembling-machine-1", "stone-furnace", "gun-turret",
  "stone-wall", "gate", "solar-panel", "accumulator", "lab", "radar", "roboport",
  "storage-tank", "pump", "offshore-pump", "boiler", "steam-engine", "small-lamp",
  "constant-combinator", "land-mine",
  "straight-rail", "curved-rail-a", "rail-signal", "rail-chain-signal", "train-stop",
}
local never_touched = {
  "character", "car", "tank", "spidertron", "locomotive", "cargo-wagon", "fluid-wagon",
  "small-biter", "biter-spawner", "small-worm-turret", "tree-01", "big-rock",
}
local base_resources = { "iron-ore", "copper-ore", "coal", "stone", "uranium-ore" }
local base_fluid_resources = { "crude-oil" }

local sa_allowed = { "big-mining-drill", "turbo-transport-belt", "turbo-underground-belt",
  "turbo-splitter", "turbo-loader", "stack-inserter" }
local sa_blocked = { "foundry", "electromagnetic-plant", "agricultural-tower", "recycler",
  "rail-ramp", "rail-support" }
local sa_never_touched = { "elevated-straight-rail", "elevated-curved-rail-a" }
local sa_resources = { "tungsten-ore", "calcite", "scrap" }
local sa_fluid_resources = { "lithium-brine", "fluorine-vent", "sulfuric-acid-geyser" }

local function concat(...)
  local out = {}
  for _, list in ipairs({ ... }) do
    for _, v in ipairs(list) do table.insert(out, v) end
  end
  return out
end

scenarios["base-defaults"] = {
  space_age = false,
  allowed = concat(base_allowed, { "splitter", "fast-splitter" }),
  blocked = base_blocked,
  untouched = never_touched,
  restricted_resources = concat(base_resources, base_fluid_resources),
}

scenarios["space-age-defaults"] = {
  space_age = true,
  allowed = concat(base_allowed, sa_allowed, { "splitter" }),
  blocked = concat(base_blocked, sa_blocked),
  untouched = concat(never_touched, sa_never_touched),
  restricted_resources = concat(base_resources, base_fluid_resources, sa_resources, sa_fluid_resources),
}

scenarios["rails-allowed"] = {
  space_age = true,
  settings = { ["opr-allow-rails"] = true },
  allowed = { "straight-rail", "curved-rail-a", "curved-rail-b", "half-diagonal-rail",
    "rail-signal", "rail-chain-signal", "train-stop", "rail-ramp", "rail-support" },
  blocked = { "assembling-machine-1", "stone-furnace" },
  untouched = sa_never_touched,
  restricted_resources = { "iron-ore" },
}

scenarios["splitters-disallowed"] = {
  space_age = false,
  settings = { ["opr-allow-splitters"] = false },
  allowed = { "transport-belt", "underground-belt", "loader" },
  blocked = { "splitter", "fast-splitter", "express-splitter" },
  restricted_resources = { "iron-ore" },
}

scenarios["fluids-unrestricted"] = {
  space_age = true,
  settings = { ["opr-include-fluid-resources"] = false },
  restricted_resources = concat(base_resources, sa_resources),
  unrestricted_resources = concat(base_fluid_resources, sa_fluid_resources),
  blocked = { "assembling-machine-1" },
}

scenarios["extra-allowed-setting"] = {
  space_age = false,
  settings = { ["opr-extra-allowed-entities"] = " radar,stone-furnace ,  small-lamp" },
  allowed = { "radar", "stone-furnace", "small-lamp" },
  blocked = { "steel-furnace", "lab", "assembling-machine-1" },
  restricted_resources = { "iron-ore" },
}

scenarios["mod-interface"] = {
  space_age = false,
  extra_mods = { { name = "opr-api-test-mod", dir = root .. "/tests/fixtures/api-test-mod" } },
  -- allowed_types["furnace"] covers every furnace, including modded ones.
  allowed = { "small-lamp", "stone-furnace", "steel-furnace", "electric-furnace" },
  blocked = { "pipe", "fast-inserter", "radar", "assembling-machine-1" },
  restricted_resources = { "iron-ore" },
  unrestricted_resources = { "coal" },
}

local scenario = assert(scenarios[scenario_name], "unknown scenario " .. tostring(scenario_name))

local data = harness.load({
  factorio_data = fd,
  mod_dir = root,
  space_age = scenario.space_age,
  settings = scenario.settings,
  extra_mods = scenario.extra_mods,
})

local collision_mask_util = require("collision-mask-util")
local default_masks = require("collision-mask-defaults")

local failures = {}
local function fail(msg) table.insert(failures, msg) end

local function find_entity(name)
  for type in pairs(default_masks) do
    local p = data.raw[type] and data.raw[type][name]
    if p then return p end
  end
end

local function mask_of(p)
  return collision_mask_util.get_mask(p)
end

local layer = data.raw["collision-layer"] and data.raw["collision-layer"][LAYER]
if not layer then fail("collision layer " .. LAYER .. " was not defined") end

local reference_ore = data.raw["resource"]["iron-ore"]

local function check_entities(list, want_layer, label)
  for _, name in ipairs(list or {}) do
    local p = find_entity(name)
    if not p then
      fail(label .. ": entity " .. name .. " does not exist")
    else
      local has = mask_of(p).layers[LAYER] == true
      if has ~= want_layer then
        fail(string.format("%s: %s (%s) %s the layer", label, name, p.type,
          has and "unexpectedly has" or "is missing"))
      end
      -- The real placement rule: blocked entities must collide with ore, others must not.
      if reference_ore and mask_of(reference_ore).layers[LAYER] then
        local collides = collision_mask_util.masks_collide(mask_of(p), mask_of(reference_ore))
        if collides ~= want_layer then
          fail(string.format("%s: %s %s with iron-ore", label, name,
            collides and "collides" or "does not collide"))
        end
      end
    end
  end
end

check_entities(scenario.allowed, false, "allowed")
check_entities(scenario.blocked, true, "blocked")
check_entities(scenario.untouched, false, "untouched")

local function check_resources(list, want_layer, label)
  for _, name in ipairs(list or {}) do
    local p = data.raw["resource"][name]
    if not p then
      fail(label .. ": resource " .. name .. " does not exist")
    elseif (mask_of(p).layers[LAYER] == true) ~= want_layer then
      fail(label .. ": resource " .. name .. (want_layer and " is missing" or " unexpectedly has") .. " the layer")
    end
  end
end

check_resources(scenario.restricted_resources, true, "restricted")
check_resources(scenario.unrestricted_resources, false, "unrestricted")

-- Invariant: world-generated entities (trees, rocks, enemies) are never
-- touched, otherwise map generation around ore would change.
for _, type in ipairs({ "tree", "simple-entity", "unit-spawner", "unit", "turret", "fish", "cliff" }) do
  for name, p in pairs(data.raw[type] or {}) do
    local flags = {}
    for _, f in pairs(p.flags or {}) do flags[f] = true end
    if not flags["player-creation"] and p.collision_mask and p.collision_mask.layers[LAYER] then
      fail("world entity " .. type .. "/" .. name .. " got the layer")
    end
  end
end

if #failures > 0 then
  for _, f in ipairs(failures) do print("  FAIL " .. f) end
  os.exit(1)
end
