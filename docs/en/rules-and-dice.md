# Rules and Dice

DiceFrame separates “what the dice rolled” from “whether the action succeeded.” The random layer only produces die values. The rule layer defines the dice system, modifiers, target, advantage/disadvantage, and success level. The GM decides whether an action genuinely needs a check and selects an appropriate attribute, skill, and difficulty.

This boundary lets D&D, CoC, cyberpunk, wuxia, and custom content packs share one stable dice implementation without embedding every setting's house rules in random-number code.

## Built-in check behavior

| Rule | Resolution | Critical behavior | Advantage and help |
|---|---|---|---|
| D&D 5e-inspired Lite | `d20 + modifier >= DC` | Ordinary ability/skill checks do not automatically succeed on a natural 20 or fail on a natural 1 | Roll 2d20 and keep high/low; effective assistance grants advantage |
| Freeform d20 (fantasy, cyberpunk, wuxia) | `d20 + modifier >= DC` | Natural 20 is a critical success and natural 1 is a critical failure by default | Roll 2d20 and keep high/low; effective assistance grants advantage |
| CoC 7e-inspired Investigation | d100 at or below the skill/attribute threshold | 1 is a critical success; fumbles follow the CoC 7e threshold; regular, hard, and extreme success levels are supported | Bonus dice keep the lower final candidate and penalty dice keep the higher one; `00 + 0` is correctly treated as 100 |
| Freeform narrative | No automatic check | None | None |

The bundled D&D and CoC options are lightweight, natural-language-friendly assisted rules, not complete reproductions of commercial rulebooks. Individual rules and house rules may add further constraints for attacks, spells, and class abilities.

## When to roll

A check should happen only when the outcome is uncertain and failure has a meaningful consequence. Routine conversation, pure roleplay, unobstructed movement, established facts, and repeated descriptions of the same action should not be forced into checks.

DiceFrame records checks per character and round so one action is not rolled again during planning, parsing, and narration. Difficulty is capped by the rule's `max_check_dc`; it does not rise automatically merely because a campaign has run for many rounds.

## Declaring checks in a content pack

Content packs should declare capabilities explicitly instead of mentioning them only in the human-readable `mechanics` field. This example enables cinematic natural 20/1 behavior for a d20 rule:

```json
{
  "dice_system": "d20",
  "max_check_dc": 20,
  "check_mechanic": {
    "dice": "d20",
    "comparison": "roll_plus_modifier_gte_target",
    "critical": {"success": 20, "failure": 1},
    "advantage": {
      "type": "d20_keep_high_low",
      "allow_explicit": true,
      "assistance_grants": "advantage"
    }
  }
}
```

For ordinary D&D ability/skill check semantics, set `critical.success` and `critical.failure` to `null`. If a rule does not support advantage/disadvantage, omit `advantage`; DiceFrame will not silently borrow that capability from another ruleset.

A world template selects a rule through `default_rule`. Lorebooks provide setting context and should not duplicate resolution algorithms. Rules may use `extends` to inherit a base template and override only the fields they intentionally change.

## Existing saves

Existing saves require no conversion. As long as their `rule_id` remains available, characters, lorebooks, and campaign logs stay intact and continue with the current dice and resolution implementation.

An external content pack that adds explicit advantage/disadvantage support must be updated and re-enabled. That update does not rewrite save narration or character sheets. Backing up `data/` before an application or pack update is still recommended.

## Pre-release checks

Audit bundled rules, installed plugins, and an additional content-pack source directory:

```powershell
python scripts\audit_rules.py --strict --path ..\content-packs
```

Simulate 25 rounds for six players and independently recompute every d20/d100 result:

```powershell
python scripts\audit_dice_campaigns.py --rounds 25 --players 6 --distribution-samples 20000 --rule-path ..\content-packs --output .codex_tmp\dice-audit.json
```

For release-scale statistics, raise `--rounds` to 10000 and `--distribution-samples` to 200000. Distribution tests only detect statistical bias; keep rule-matrix, long-campaign recomputation, and real API interaction tests as separate checks.
