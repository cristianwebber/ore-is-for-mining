-- Resources get this layer, and so does every building that is not allowed on
-- them, so the game itself refuses to place those buildings (and their ghosts).
data:extend({
  {
    type = "collision-layer",
    name = "opr_resource",
  },
})

-- Public interface for other mods. Add a dependency on "ore-is-for-mining"
-- (optional "? ore-is-for-mining" is fine) and, in data or data-updates:
--
--   if ore_is_for_mining then
--     ore_is_for_mining.allowed_types["my-type"] = true       -- allow a whole entity type
--     ore_is_for_mining.allowed_entities["my-entity"] = true  -- allow a single entity
--     ore_is_for_mining.blocked_entities["my-entity"] = true  -- force-block an entity
--     ore_is_for_mining.ignored_resources["my-ore"] = true    -- leave a resource unrestricted
--   end
ore_is_for_mining = {
  allowed_types = {},
  allowed_entities = {},
  blocked_entities = {},
  ignored_resources = {},
}
