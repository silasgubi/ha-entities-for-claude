---
name: ha-entities
description: Query the real entities of my Home Assistant instance (JSON registries in .storage + live states via REST API). USE whenever you need to know which entities exist, their exact entity_ids, areas, current states, or to validate entity_ids while planning or writing HA automations, dashboards and packages. Never guess entity_ids: look them up first.
---

# HA Entities: query Home Assistant entities

Tool so you are never "in the dark" about the real HA entities when planning
projects, writing automations or reviewing YAML.

## Data source

HA's JSON "database" lives in `<config>/.storage` (reading is safe while HA
is running; **NEVER write to these files**):

- `core.entity_registry`: all entities, with name, platform, disabled/hidden, aliases
- `core.device_registry`: devices (inherited area, manufacturer, model)
- `core.area_registry`: areas

Current states come from the REST API (`$HA_URL/api/states`, long-lived token).

## Configuration

<!-- Fill these in for your setup. Keep the token OUT of this file if the
     skill directory is ever shared: prefer setting HA_TOKEN in your shell
     profile or a local .env you don't commit. -->

```
HA_STORAGE_PATH = <path to your .storage, e.g. \\homeassistant\config\.storage or /config/.storage>
HA_URL          = http://homeassistant.local:8123
HA_TOKEN        = <long-lived access token, created at $HA_URL/profile/security>
```

## Usage

```
python <path-to>/ha_entities.py [options]
```

| Option | Effect |
|---|---|
| `--summary` | total + count per domain |
| `--areas` | list areas with entity counts |
| `--domain light` | filter by domain |
| `--area kitchen` | filter by area (partial match) |
| `--search thermostat` | search entity_id, name, device and aliases |
| `--states` | include current state via REST API (needs network + token) |
| `--disabled` / `--enabled-only` | filter by status |
| `--json` | full JSON output (includes aliases, platform, device_class) |

Options combine: `--domain sensor --search temperature --states`.

## Recommended flow when planning projects

1. `--summary` or `--areas` for the big picture.
2. `--search <term>` or `--domain <dom> --area <area>` to find candidates.
3. `--states` on the candidates to confirm they are alive (not `unavailable`).
4. Only then write YAML using the exact entity_ids returned.

## Lessons learned

- **Don't query the recorder SQLite (`home-assistant_v2.db`) for this**: it's
  large, may be locked or corrupted, and it only knows about entities with
  recorded history. The JSON registries are the source of truth for *what
  exists*; the REST API for *current state*.
- **Many entities are disabled** (often a third of them): use
  `--enabled-only` when hunting for entities to automate.
- **Suffixes like `_2`, `_v2`, `_old`** usually mean duplicates, but not
  always (integrations with two accounts create legitimate `_2` entities).
  Check the area/device before treating them as garbage.
- Entities without their own `area_id` inherit the device's area (the script
  already resolves this).
