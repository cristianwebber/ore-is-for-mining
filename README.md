# Ore is for Mining

Every engineer knows the story. You drop a few furnaces "just for now" next to the drills, and 30 hours later a whole factory sits on top of your best iron patch.

This mod ends that. On ore and oil, you can only build what a mining outpost actually needs:

- **Mining drills** (including pumpjacks)
- **Belts, underground belts, splitters and loaders**
- **Inserters**
- **Chests** (wooden, iron, steel and logistic chests)
- **Beacons**
- **Electric poles**
- **Pipes and pipes-to-ground**

Everything else (assemblers, furnaces, turrets, walls, solar panels and so on)? Find your own land.

> **Note:** this mod's code was generated with AI (Claude) and tested by a human in-game.

## How it works

The restriction uses the game's own collision system. Placing a blocked building on ore works like placing it on water: the build preview turns red and it can't be placed. That applies to ghosts, blueprints and construction robots too, so nothing slips through.

- Works on **ore and fluid patches**: crude oil, plus Space Age's tungsten, calcite, scrap, lithium brine, fluorine vents and sulfuric acid geysers.
- **Mod friendly:** the rules go by building type, so drills, belts, loaders, inserters, chests, beacons, poles and pipes from other mods are allowed automatically, and their other buildings and resources are restricted automatically.
- **Vehicles, trains and elevated rails are never restricted.** You can still drive across your patches and run elevated rails over them. Rail supports and ramps count as rails, though, so a patch too wide to span needs the "Allow rails" setting.
- Buildings already standing on ore in an existing save are left alone.

## Settings (startup)

| Setting | Default | Description |
|---|---|---|
| Allow rails on resource patches | Off | Rails, rail ramps, rail supports, signals and train stops. Turn this on to put elevated rail supports on wide patches. |
| Allow splitters on resource patches | On | Splitters and lane splitters |
| Also apply to oil and other fluid resources | On | On: crude oil spots (and Space Age's lithium brine, fluorine vents and sulfuric acid geysers) follow the same rules as ore. Off: only solid ores are restricted. |
| Extra allowed entities | (empty) | Comma-separated entity names, e.g. `small-lamp, radar, lab` |

## Compatibility

- Factorio 2.1, with or without Space Age.
- Mods that replace entity collision masks in their own `data-final-fixes` after this mod loads can undo the restriction for those entities.

## For mod authors

Add `"? ore-is-for-mining"` as an optional dependency and adjust the rules during the data stage (`data.lua` or `data-updates.lua`):

```lua
if ore_is_for_mining then
  ore_is_for_mining.allowed_types["my-type"] = true        -- allow a whole entity type
  ore_is_for_mining.allowed_entities["my-entity"] = true   -- allow a single entity
  ore_is_for_mining.blocked_entities["my-entity"] = true   -- force-block an entity
  ore_is_for_mining.ignored_resources["my-ore"] = true     -- leave a resource unrestricted
end
```

## License

The code is under the MIT license. The thumbnail is made from Factorio's own graphics, which belong to Wube Software.

- Mod portal: https://mods.factorio.com/mod/ore-is-for-mining
- Source: https://github.com/cristianwebber/ore-is-for-mining
