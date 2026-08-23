"""D&D 5e Lite 规则化整改回归：伤害/护甲/暴击/DC 均按规则 capability 驱动。

通用 d20（base_d20/freeform_fantasy）保持旧版 hp_based 语义；
dnd5e 三语模板 mechanics 必须一致。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.engine.character_utils import build_starter_items
from src.engine.checks import _attack_target_dc
from src.engine.combat import calc_hp_based_damage, resolve_attack
from src.engine.dice import d20_dc_cap
from src.rules.rule_system import RuleSystem

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "templates" / "rules"


def _rule(name: str) -> RuleSystem:
    return RuleSystem.load(RULES / name)


def test_dnd5e_declares_lite_mechanics_and_base_d20_keeps_legacy() -> None:
    dnd = _rule("dnd5e.json")
    assert dnd.damage_mechanic == {
        "armor_reduces_damage": False,
        "degree_affects_damage": False,
        "critical_damage": "double_damage_dice",
    }
    assert dnd.armor_model == "category_lite"
    assert d20_dc_cap(dnd) == 30

    base = _rule("base_d20.json")
    assert base.damage_mechanic == {
        "armor_reduces_damage": True,
        "degree_affects_damage": True,
        "critical_damage": "double_total",
    }
    assert base.armor_model == "sum"
    assert d20_dc_cap(base) == 20


def test_dnd5e_mechanics_identical_across_languages() -> None:
    zh = json.loads((RULES / "dnd5e.json").read_text(encoding="utf-8"))
    en = json.loads((RULES / "dnd5e_en.json").read_text(encoding="utf-8"))
    ja = json.loads((RULES / "dnd5e_ja.json").read_text(encoding="utf-8"))
    keys = ["check_mechanic", "damage_mechanic", "armor_model", "max_check_dc", "dc_table"]
    for other in (en, ja):
        for key in keys:
            assert zh[key] == other[key], key


def test_legacy_fixed_damage_path_unchanged() -> None:
    check = {"verdict": "成功", "is_critical": True, "dice_system": "d20", "total": 20}
    # 旧版：总值×2（含修正），再减护甲
    assert calc_hp_based_damage(7, 1, 2, check) == (7 + 1) * 2 - 2
    # 程度成功追加
    normal = {"verdict": "成功", "is_critical": False, "dice_system": "d20", "total": 19}
    assert calc_hp_based_damage(7, 1, 2, normal) == 7 + 1 + (19 - 10) // 3 - 2


def test_dnd5e_armor_does_not_reduce_and_degree_does_not_add() -> None:
    dnd = _rule("dnd5e.json")
    mech = dnd.damage_mechanic
    normal = {"verdict": "成功", "is_critical": False, "dice_system": "d20", "total": 25}
    # 高总值不追加伤害；护甲不减伤
    assert calc_hp_based_damage(7, 1, 5, normal, mechanic=mech) == 8


def test_dnd5e_critical_doubles_damage_dice_only(monkeypatch) -> None:
    dnd = _rule("dnd5e.json")
    target = {
        "character_name": "靶子",
        "attributes": {"dex": 10},
        "equipment": [{"name": "皮甲", "armor": 2}],
        "hp": 50,
        "max_hp": 50,
    }
    weapon = {"name": "长剑", "damage": 7, "damage_dice": "1d8"}
    check = {"check_id": "c1", "verdict": "成功", "is_critical": True, "dice_system": "d20"}
    rolls = iter([5, 7])
    monkeypatch.setattr("random.randint", lambda _a, _b: next(rolls))

    result = resolve_attack(
        "攻击者", target, weapon, attr_value=12, check_result=check, rule=dnd
    )

    # 5+7 伤害骰 + 1 属性修正；护甲不再减伤；固定修正不翻倍
    assert result.actual_damage == 13


def test_dnd5e_non_critical_rolls_single_damage_die(monkeypatch) -> None:
    dnd = _rule("dnd5e.json")
    target = {"character_name": "靶子", "attributes": {"dex": 10}, "hp": 50, "max_hp": 50}
    weapon = {"name": "长剑", "damage": 7, "damage_dice": "1d8"}
    check = {"check_id": "c2", "verdict": "成功", "is_critical": False, "dice_system": "d20"}
    rolls = iter([5])
    monkeypatch.setattr("random.randint", lambda _a, _b: next(rolls))

    result = resolve_attack(
        "攻击者", target, weapon, attr_value=12, check_result=check, rule=dnd
    )

    assert result.actual_damage == 6


def test_category_lite_ac_by_armor_category() -> None:
    dnd = _rule("dnd5e.json")
    dex18 = {"dex": 18}  # 修正 +4

    unarmored = _attack_target_dc(dnd, {"attributes": dex18, "equipment": []})
    assert unarmored == 14  # 10 + 4

    light = _attack_target_dc(
        dnd, {"attributes": dex18, "equipment": [{"name": "皮甲"}, {"name": "盾牌"}]}
    )
    assert light == 11 + 4 + 2

    medium = _attack_target_dc(
        dnd, {"attributes": dex18, "equipment": [{"name": "链甲"}, {"name": "盾牌"}]}
    )
    assert medium == 13 + 2 + 2  # DEX 封顶 +2

    heavy = _attack_target_dc(dnd, {"attributes": dex18, "equipment": [{"name": "板甲"}]})
    assert heavy == 18  # 重甲不吃 DEX


def test_legacy_rules_keep_sum_armor_ac(tmp_path) -> None:
    rule_file = tmp_path / "sum_armor.json"
    rule_file.write_text(
        json.dumps(
            {
                "rule_id": "sum_armor",
                "dice_system": "d20",
                "attributes": [{"key": "dex", "name": "敏捷", "min": 3, "max": 20}],
                "check_mechanic": {
                    "dice": "d20",
                    "comparison": "roll_plus_modifier_gte_target",
                    "critical": {},
                    "attack_target": {"type": "armor_class", "base": 10, "attribute": "dex"},
                },
            }
        ),
        encoding="utf-8",
    )
    rule = RuleSystem.load(rule_file)
    total = _attack_target_dc(
        rule, {"attributes": {"dex": 18}, "equipment": [{"name": "皮甲", "armor": 2}]}
    )
    assert total == 10 + 4 + 2


def test_starter_items_carry_damage_dice_for_known_weapons() -> None:
    dnd = _rule("dnd5e.json")
    equip, _inv = build_starter_items(dnd, "战士")
    sword = next(item for item in equip if item["name"] == "长剑")
    assert sword["damage_dice"] == "1d8"
