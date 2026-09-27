-- Resources get this layer, and so does every building that is not allowed on
-- them, so the game itself refuses to place those buildings (and their ghosts).
data:extend({
  {
    type = "collision-layer",
    name = "opr_resource",
  },
})

-- Public interface for other mods. Add a dependency on "ore-patch-restrictions"
-- (optional "? ore-patch-restrictions" is fine) and, in data or data-updates:
--
--   if ore_patch_restrictions then
--     ore_patch_restrictions.allowed_types["my-type"] = true       -- allow a whole entity type
--     ore_patch_restrictions.allowed_entities["my-entity"] = true  -- allow a single entity
--     ore_patch_restrictions.blocked_entities["my-entity"] = true  -- force-block an entity
--     ore_patch_restrictions.ignored_resources["my-ore"] = true    -- leave a resource unrestricted
--   end
ore_patch_restrictions = {
  allowed_types = {},
  allowed_entities = {},
  blocked_entities = {},
  ignored_resources = {},
}
