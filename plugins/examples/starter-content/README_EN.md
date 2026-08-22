# Starter Content Example

[中文](README_CN.md) | English

This DiceFrame `content-pack` example contributes a rule, world template, character template, NPC, item, spell, and class.

## Package

```powershell
python scripts\package_plugin.py plugins\examples\starter-content --overwrite
```

The zip is written to `dist/plugins/` and can be installed under Settings → Plugins → Install plugin.

## Current Behavior

- Rules appear in the rule list.
- The example rule explicitly declares d20 total checks, natural 20/1, and advantage/disadvantage so content authors can copy and adapt it safely.
- World templates appear during game creation.
- Character templates can be imported into the character-card library from plugin settings.
- NPCs, items, spells, and classes can be imported into a selected lorebook.

This example starts no background process and makes no external network request.

Before publishing a content pack, run the rule audit and a short campaign simulation:

```powershell
python scripts\audit_rules.py --strict --path plugins\examples\starter-content
python scripts\audit_dice_campaigns.py --rounds 25 --players 6 --rule-path plugins\examples\starter-content --rule example_rule
```
