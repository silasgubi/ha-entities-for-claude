# 🏠🔍 HA Entities for Claude

**Give Claude Code (or any coding agent) real knowledge of your Home Assistant entities — with one dependency-free Python script.**

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/works%20with-Home%20Assistant-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)

Ever asked an AI assistant to write a Home Assistant automation and watched it
**invent entity IDs that don't exist**? `light.living_room_main` sounds
plausible — but your actual entity is `light.sonoff_1000a1b2c3`. The AI can't
know that. Unless you show it.

This repo is the fix: a small script that reads Home Assistant's own JSON
registries and answers, instantly and accurately:

- *Which entities exist?* (with exact `entity_id`s)
- *What room is each one in? What device does it belong to?*
- *Which ones are disabled, hidden, or duplicated?*
- *What's their state right now?*

Plus a ready-made **Claude Code skill** so your agent looks entities up
automatically instead of guessing.

```
$ python scripts/ha_entities.py --search coffee --states

switch.coffee_maker = off (Kitchen) | Coffee Maker
sensor.coffee_maker_power = 0.0 W (Kitchen) | Coffee Maker Power

2 entities
```

---

## 💡 The insight: HA has a JSON database

Most attempts to export HA entities go straight to the recorder database
(`home-assistant_v2.db`). That's the wrong tool: it's hundreds of MB, often
locked or corrupted, and it only knows about entities with recorded history.

Home Assistant keeps its **actual source of truth** in three small JSON files
under `<config>/.storage/`:

| File | What's inside |
|---|---|
| `core.entity_registry` | Every entity: `entity_id`, name, platform, disabled/hidden status, voice aliases |
| `core.device_registry` | Every device: manufacturer, model, area |
| `core.area_registry` | Your rooms |

Reading them is instant, needs no add-ons, and works even while HA is running.
Entities that don't declare their own area inherit the device's area — the
script resolves that join for you. For **live states**, the standard REST API
(`/api/states`) fills the gap.

> ⚠️ **Read-only!** Never write to `.storage` files — HA owns them.
> Reading is safe; writing can corrupt your instance.

---

## 🚀 Quick start

**1. Get the script** (no install, no pip):

```bash
git clone https://github.com/silasgubi/ha-entities-for-claude.git
cd ha-entities-for-claude
```

**2. Point it at your `.storage`:**

| Where you run it | Typical path |
|---|---|
| On the HA host / SSH add-on | `/config/.storage` |
| Another machine, Samba add-on share | `\\homeassistant\config\.storage` (Windows) or your mount point |
| HA Container | `<your config volume>/.storage` |

```bash
export HA_STORAGE_PATH=/config/.storage        # or use --storage
```

**3. Query away:**

```bash
python scripts/ha_entities.py --summary          # totals per domain
python scripts/ha_entities.py --areas            # entity count per room
python scripts/ha_entities.py --domain light     # all lights
python scripts/ha_entities.py --area kitchen     # everything in the kitchen
python scripts/ha_entities.py --search motion    # fuzzy search everywhere
```

**4. (Optional) live states** — create a long-lived token at
`http://your-ha:8123/profile/security`, then:

```bash
export HA_URL=http://homeassistant.local:8123
export HA_TOKEN=eyJhbGci...
python scripts/ha_entities.py --domain climate --states
```

```
climate.bedroom = cool (Bedroom) | Air Conditioner
climate.living_room = off (Living Room) | AC Living Room

2 entities
```

---

## 🤖 Turn it into a Claude Code skill

The real payoff: make your coding agent **look up entities before writing
YAML**, automatically.

1. Copy the skill folder:

   ```bash
   mkdir -p ~/.claude/skills/ha-entities/scripts
   cp skill/SKILL.md ~/.claude/skills/ha-entities/
   cp scripts/ha_entities.py ~/.claude/skills/ha-entities/scripts/
   ```

2. Edit `~/.claude/skills/ha-entities/SKILL.md` — fill in your paths in the
   **Configuration** section (and keep your token in an env var, not in the
   file).

3. That's it. Next time you ask Claude Code to *"write an automation that
   turns off the kitchen lights when there's no motion"*, it will query your
   real registry, find `binary_sensor.kitchen_presence` and
   `light.kitchen_spots`, verify they're enabled and available — and only
   then write the YAML.

The skill's `description` field tells Claude *when* to use it ("whenever you
need to know which entities exist... never guess entity_ids"). See
[`skill/SKILL.md`](skill/SKILL.md).

---

## 📋 All options

| Option | Effect |
|---|---|
| `--summary` | total + count per domain |
| `--areas` | list areas with entity counts |
| `--domain <d>` | filter by domain (`light`, `sensor`, ...) |
| `--area <a>` | filter by area name (partial match) |
| `--search <q>` | search entity_id, friendly name, device name and aliases |
| `--states` | add current state from the REST API |
| `--disabled` | only disabled entities |
| `--enabled-only` | hide disabled entities |
| `--json` | machine-readable output (aliases, platform, device_class included) |
| `--storage`, `--url`, `--token` | override `HA_STORAGE_PATH`, `HA_URL`, `HA_TOKEN` |

Options combine freely: `--domain sensor --area bedroom --search temp --states --json`.

---

## 🎓 Lessons learned (the hard way)

This project distilled out of a much bigger home-analytics system that turned
out to be overkill. What survived is what actually mattered day to day:

- **The recorder SQLite is a trap** for entity discovery. It's huge, slow over
  network shares, gets corrupted, and misses entities without history. The
  `.storage` registries are small, complete and always current.
- **Expect a third of your entities to be disabled.** Integrations create far
  more entities than you enable. Use `--enabled-only` when hunting for
  automation targets, and `--disabled` when auditing.
- **`_2` suffixes lie.** Usually they're duplicate-registration garbage, but
  sometimes they're legitimate (an integration with two accounts). Check the
  device/area before deleting anything.
- **Friendly names are for humans, entity_ids are for YAML.** An AI assistant
  needs both, plus the aliases users say out loud — that's why the script
  searches all of them.

---

## 🗣️ Bonus: expose entities *inside* HA's voice assistant

If you use HA's conversation agents (Assist with an LLM), the same problem
exists in reverse: the LLM needs to know your entities. In the agent's system
prompt template you get an `exposed_entities` variable:

```jinja2
{% raw %}{% for entity in exposed_entities | sort(attribute='area_name') %}
{% if loop.changed(entity.area_name) %}
### Area: {{ entity.area_name or 'No area' }}
{% endif %}
- {{ entity.name }} ({{ entity.entity_id }}) [{{ entity.state }}]
  {%- if entity.aliases %} — aliases: {{ entity.aliases | join(', ') }}{% endif %}
{% endfor %}{% endraw %}
```

Grouping by area and including aliases makes voice commands dramatically more
reliable. Control what's listed via **Settings → Voice assistants → Expose**.

---

## 🔐 Security notes

- The long-lived token grants full API access — treat it like a password.
  Keep it in an environment variable or a local `.env`; never commit it.
- `.storage` files contain no passwords, but they do reveal your device
  inventory — don't publish raw dumps.
- Everything here is **read-only** against HA. The script never calls a
  service or writes anything.

## 🤝 Alternatives

- [Home Assistant MCP integrations](https://www.home-assistant.io/integrations/mcp_server/) —
  richer (can call services), but requires MCP setup and a running server.
  This repo's approach is deliberately simpler: one file, stdlib only, works
  offline against a file share, easy to audit.
- `homeassistant.exposed_entities` in templates — only inside HA itself (see
  the bonus section above).

## 📄 License

[MIT](LICENSE) — do whatever you want, no warranty.

---

*Built from real-world lessons automating a very opinionated smart home in
São Paulo, Brazil. If this saved you from `light.living_room_that_doesnt_exist`,
a ⭐ is appreciated!*
