# DiceFrame Architecture Source of Truth

This document describes the current implementation, not a roadmap. The dependency direction is `routes -> WebAPI -> services -> core`; core code must not import `src.webui`, WebAPI methods are delegates, and cross-service calls go through API delegates.

## Content V2

Inputs cross a compatibility boundary before entering the current canonical model:

```text
Legacy / V1 Rule / Plugin / Save / World / Character
                    ↓
              Compatibility
                    ↓
          Canonical Current Model
                    ↓
            Runtime Mechanics
                    ↓
             Typed Locale
                    ↓
                   UI
```

Canonical identity is a stable reference key: `fighter`, `longsword`, `chain_mail`, `athletics`, `str`, and `npc_innkeeper`. `战士 / Fighter`, `长剑 / Longsword / ロングソード`, and `老汤姆 / Old Tom` are display text only. Changing language never changes an ID.

Canonical rule/content data is the mechanics authority for normal V2 runtime. Legacy tables such as `ARMOR_LITE`, `WEAPON_DAMAGE`, and `WEAPON_DAMAGE_DICE` are compatibility fallbacks for old saves or V1 input only.

## Rule Locale

The rule core owns `dice_system`, `damage_dice`, `ac_base`, `dex_cap`, `attribute_points`, `proficiency`, `combat_model`, `skill_pools`, `item_categories`, damage/death mechanics, permissions, capabilities, and scripts. Profession skill pools use canonical class and skill IDs. Typed locales may translate their display names but cannot replace skill pools or item classifiers. Unknown or mechanics-shaped nested fields are rejected.

## World Locale

The world core owns `world_id`, `default_rule`, `recommended_rules`, `suggested_difficulty`, and the starter lorebook entry set/order, IDs, types, tiers, `unreliable`, `sync_on_enter`, `triggers_recursive`, `visible_to`, `match_mode`, `sticky`, `cooldown`, `delay`, `order`, `probability`, `group`, `group_weight`, `connected_to`, and other deterministic fields.

World locale may change only `world_name`, `description`, `world_setting`, `starter_scene`, and `name`, `keywords`, or `content` for a canonical lore entry ID. World Locale cannot replace `starter_lorebook` entries. Language changes cannot add, remove, or rename canonical lore identities.

For example, core ID `npc_innkeeper` may have `npc_innkeeper.name = 老汤姆` in Chinese and `npc_innkeeper.name = Old Tom` in English. The identity remains `npc_innkeeper`.

The lorebook database stores canonical/core entries. Keyword matching, prompt construction, and puzzle initialization build a read-only localized view for each `GameInstance.language`; translated text is never written back to the shared database.

## Plugin Content V2

The manifest currently supports `schema_version = 1`, `content_schema_version = 1 or 2`, `locale_schema_version = 1`, and `default_locale` as the package locale fallback. Locale fallback is exact requested locale -> base locale -> package/default locale -> base(default locale) -> canonical/core display fallback.

`ResourceRef` examples are `core:item:longsword` and `plugin:my-pack:item:moon_blade`. Ordinary V2 item/class/spell/npc/character_template resources can coexist through namespaces. Rules and worlds still primarily use plain `rule_id` / `world_id`, so duplicate Rule/World IDs across V2 plugins are explicitly rejected; there is no first-wins or last-wins behavior.

V2 resource IDs must already be canonical. The registry never silently normalizes case, spaces, or non-ASCII IDs on a plugin's behalf. When V2 locale or content validation fails, catalog APIs return `CONTENT_VALIDATION_FAILED`; they do not omit the broken resource or fall back to unlocalized content. The in-app content-pack exporter always emits a Content V2 core plus typed-locale layout. V1 full copies remain supported only through import adapters.

## Migration and Compatibility

`src/migrations/` performs persisted schema upgrades. `src/compat/` adapts old external/runtime shapes to the current canonical model. V1 packages are read through adapters; compatibility branches do not move into normal business logic.

Migrations for loaded persisted `GameInstance` data are orchestrated through the single `src.migrations.migrate_instance` entry point. Domain-specific migration implementations may live in `src/compat/` as pure adapters, but services, routes, and runtimes must not call those adapters directly. Every migration must be idempotent, tested, and bounded by an explicit version/identity/digest contract; uncertain migrations fail closed. New behavior adds a versioned migration step rather than changing the meaning of a released step.

## Application Update Boundary

Windows source/portable and managed Docker share the download state machine in `src/webui/services/updater.py`, but installation authority is separated. Source updates use a backup transaction, portable candidates are committed by the Windows launcher, and Docker candidates are committed only by the stable image launcher under `src/docker_launcher/` after health and probation checks pass. A Docker application process may write only a restart signal containing a relative candidate path; it cannot control the Docker daemon, mount the Docker socket, or overwrite the current version directory.

Docker Update schema 1 binds the application version, `linux-amd64`, CPython ABI, launcher schema, base runtime API, and `data_rollback_safe`. The package builder, application updater, and launcher reuse the same contract validation; checksum, platform, ABI, runtime, data-rollback declaration, and path-safety failures are all fail closed. Versioned application payloads live under `data/_updater/docker-versions/`; business-data migrations remain owned by `src/migrations/`, and rolling back application files never pretends to roll back a data schema.

Runtime logs are owned centrally by `src/runtime_logging.py`; launchers and business services must not implement separate rotation or retention policies. Portable logs live under the installation-root `logs/`, managed Docker logs under persistent `data/logs/`, and the default retention is 30 days. The clear operation may remove only DiceFrame runtime logs and must never touch game history, saves, or third-party logs.

## Frontend and Rule Boundaries

The backend materializes V2 locales and the frontend renders the returned payload; the frontend does not reimplement Content V2 locale architecture. D&D using d20 is not the same as changing generic d20 behavior. D&D-specific behavior remains inside the D&D boundary.

## Adventure Bundle v1

Advanced play has four independent inputs: the Ruleset Runtime supplies mechanics, the Worldbook supplies setting and lore, an optional Adventure Bundle supplies a story graph, scenes, NPCs, map locations, and adventure-specific encounters, and the Coach provides local presentation-only help. With no Adventure Bundle bound, the game is standard free play and must not silently load a fixed tutorial story.

Standalone adventures live at `templates/adventures/<directory_id>/` and use `diceframe:adventure-graph-v1`. Their manifest declares a canonical adventure ID, version, world policy, and minimum runtime contract. Creation validates rules, runtime, format, and world compatibility before immutably storing `adventure_id / version / format / content_digest / world_id`. Restart preserves and revalidates that exact binding; missing or changed content and fixed-world mismatches fail closed. See `docs/adventures/ADVENTURE_BUNDLE_EN.md`.

At startup, bundled adventures are synchronized as complete directories into `data/templates/adventures/`; the D&D runtime, catalogue API, and management API all read that runtime directory. Built-in packages are read-only. Custom packages have independent canonical identities and may be copied, validation-edited, imported/exported as ZIP files, or deleted. A package referenced by any save cannot be edited or deleted because that would break its pinned digest and deterministic restart. Every write is staged and fully validated through the same `AdventureBundleLoader` before replacing the live directory.

An adventure step may replace the current story entry but never the selected Worldbook. Narrative context always includes the actual Worldbook setting, starter scene, and matched lore. Adventure completion returns to standard free play in that same world instead of a terminal tutorial page.

## D&D 2024 Authoritative Play State

`core:dnd2024` combat, Session 0, and campaign records share `GameInstance.ruleset_state.version` and one EventBatch ledger. An optional adventure supplies story input through its exact binding but is not part of the Ruleset Bundle. Combat and campaign events have separate reducers; the runtime composition root dispatches explicit intent types without making the generic engine import D&D code.

The mechanics authority for an advanced-rules character is `ruleset_character`. Creation, shared-library import/edit, joining a game, in-game profile editing, advancement, and rest all go through the `character_lifecycle` capability; legacy top-level character fields are compatibility projections only. Profile edits cannot overwrite abilities, HP, AC, advancement history, or runtime/content/state versions. Mechanical changes are revalidated or replayed from canonical choices and history.

Every Session 0 revision clears stale consent and can be locked only after all current players accept. Tasks, clues, facts, important items, and relationships enter a pending proposal before a separate GM intent confirms or rejects them. Chapter summaries are deterministic projections of confirmed events and are copied to long-term memory only after the authoritative save succeeds.

Free-text actions continue through DiceFrame's single `/action` round loop: solo play advances immediately, while multiplayer waits for every active, present character before one combined adjudication and GM response. The D&D runtime only adds read-only authoritative combat, campaign, and current-adventure state to that same LLM context; the selected Worldbook and matched lore still come from the generic narrative pipeline. The LLM cannot create campaign facts, spend resources, or advance authoritative adventure steps.

The frontend retains the generic single timeline, single action composer, character cards, party state, map, scene gallery, rule help, Worldbook, and GM controls. The left-side `DND5E Tools` entry contains only the D&D-specific adventure/campaign and authoritative combat tools; it does not create a second message stream or narrative submission endpoint. An adventure encounter gate opens combat automatically. In free play, either an explicit GM adjudication that initiative has begun or a player attack recognized by the shared check planner creates an advisory `encounter_request` that wakes the tool; encounter selection, initiative, and every mechanical result still require authoritative combat intents. Completion returns to the same public timeline.

The runtime composition root derives story encounter access from canonical adventure steps and passes an `EncounterAccess` capability into combat; campaign and combat engines do not import each other. Combat events persist a canonical encounter instance ID, preset, and origin step, and completion enters bounded history. Campaign gates accept only the matching encounter identity, so a consumed adventure encounter cannot restart. Enemy turns are resolved automatically by the server through the same validation, event, and reducer pipeline; each player can control only their own character and other players receive an explicit waiting state. Scenes, NPCs, and map locations use canonical Adventure Bundle references; locales materialize display fields only. Direct-connect player intents use an explicit field allowlist.
