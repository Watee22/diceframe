"""统一检定请求：从玩家行动生成规则无关的 CheckRequest，并完成原始掷骰。"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from src.engine.dice import (
    check_d100_bonus,
    coc_success_level,
    d20_critical_thresholds,
    d20_dc_cap,
    d20_verdict,
    roll,
)
from src.engine.game_instance import GameInstance
from src.engine.language import localized_text
from src.rules.rule_system import RuleSystem

logger = logging.getLogger("trpg")


def _load_fallback_intents() -> dict:
    """加载全局兜底词表（数据驱动，支持多语言）。

    供没有自带 intents 词表的规则使用。放 templates/rules/fallback_intents.json：
    - intents: {intent_id: {aliases: {lang: [...]}, skill_candidates, default_attribute}}
    - generic_check_words: {lang: [...]} 通用检定词
    """
    path = Path(__file__).resolve().parents[2] / "templates" / "rules" / "fallback_intents.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("通用检定兜底词表加载失败: %s", exc)
        return {}


_FALLBACK_INTENTS: dict = _load_fallback_intents()


def _fallback_intent_specs(language: str) -> list[tuple[str, tuple[str, ...], tuple[str, ...], str]]:
    """兜底意图表（数据驱动），结构同旧 _INTENT_SPECS：[(intent, aliases, skills, attr)]。"""
    result: list[tuple[str, tuple[str, ...], tuple[str, ...], str]] = []
    intents = _FALLBACK_INTENTS.get("intents") or {}
    lang = localized_text(language, {"en": "en", "zh-CN": "zh-CN", "ja": "ja"})
    for intent, block in intents.items():
        aliases = block.get("aliases") or {}
        skills = block.get("skill_candidates") or {}
        alias_list = tuple(aliases.get(lang) or aliases.get("en") or aliases.get("zh-CN") or ())
        skill_list = tuple(skills.get(lang) or skills.get("en") or skills.get("zh-CN") or ())
        if not alias_list:
            continue
        result.append((intent, alias_list, skill_list, str(block.get("default_attribute") or "")))
    return result


def _fallback_generic_words(language: str) -> tuple[str, ...]:
    """兜底通用检定词（按语言取，回退英文再中文）。"""
    words = _FALLBACK_INTENTS.get("generic_check_words") or {}
    lang = localized_text(language, {"en": "en", "zh-CN": "zh-CN", "ja": "ja"})
    return tuple(words.get(lang) or words.get("en") or words.get("zh-CN") or ())


def _normalized(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _skill_name(skill: object) -> str:
    if isinstance(skill, dict):
        return str(skill.get("name") or "").strip()
    return str(skill or "").strip()


def _find_skill(character_sheet: dict, text: str, candidates: tuple[str, ...]) -> str:
    skills = character_sheet.get("skills", [])
    names = [_skill_name(skill) for skill in skills]
    direct = [name for name in names if name and _normalized(name) in text]
    if direct:
        return max(direct, key=len)
    for candidate in candidates:
        for name in names:
            if name and (_normalized(candidate) in _normalized(name) or _normalized(name) in _normalized(candidate)):
                return name
    return ""


def _attribute_name(rule: RuleSystem | None, key: str) -> str:
    if rule:
        for attribute in rule.attributes:
            if attribute.get("key") == key:
                return str(attribute.get("name") or key)
    return key


def detect_advantage_mode(text: str, action: dict, rule: RuleSystem | None) -> tuple[str, str]:
    if not rule:
        return "", ""
    capability = rule.advantage_mechanic
    kind = str(capability.get("type") or "")
    if not kind or not capability.get("allow_explicit"):
        return "", ""
    raw_mode = str(action.get("advantage_mode") or action.get("advantage") or "").strip().lower()
    if kind == "coc_bonus_penalty":
        has_bonus = raw_mode in {"advantage", "奖励骰", "bonus"} or "奖励骰" in text
        has_penalty = raw_mode in {"disadvantage", "惩罚骰", "penalty"} or "惩罚骰" in text
        if has_bonus and has_penalty:
            return "", "奖励骰与惩罚骰同时存在，已抵消"
        if has_bonus:
            return "advantage", "奖励骰：共享个位，额外十位取较低最终值"
        if has_penalty:
            return "disadvantage", "惩罚骰：共享个位，额外十位取较高最终值"
        return "", ""
    if kind != "d20_keep_high_low":
        return "", ""
    has_advantage = raw_mode in {"advantage", "优势", "有利", "bonus"} or any(
        word in text for word in ("优势", "有利", "占优", "奖励骰", "帮忙", "协助", "偷袭", "高地")
    )
    has_disadvantage = raw_mode in {"disadvantage", "劣势", "不利", "penalty"} or any(
        word in text for word in ("劣势", "不利", "受阻", "惩罚骰", "黑暗", "负伤", "疲惫", "干扰")
    )
    if has_advantage and has_disadvantage:
        return "", "优势与劣势同时存在，已抵消"
    if has_advantage:
        return "advantage", "优势：2d20 取高"
    if has_disadvantage:
        return "disadvantage", "劣势：2d20 取低"
    return "", ""


def build_check_request(
    instance: GameInstance,
    action: dict,
    rule: RuleSystem | None,
) -> dict[str, Any] | None:
    """为单个玩家行动生成结构化检定请求；不需要检定时返回 None。"""
    uid = str(action.get("user_id") or "")
    if uid not in instance.players:
        return None
    dice_system = str(rule.dice_system if rule else "d20").lower()
    if dice_system == "none":
        return None

    text = _normalized(action.get("text"))
    selected_skill = str(action.get("selected_skill") or "").strip()
    selected_attribute = str(action.get("selected_attribute") or "").strip()
    character_sheet = instance.get_character_sheet(uid)
    intent = ""
    candidates: tuple[str, ...] = ()
    attribute = selected_attribute

    # 意图识别：优先规则词表（数据驱动），规则未带词表时回退到全局兜底词表。
    intent = rule.find_intent(action.get("text"), instance.language, dice_system) if rule else ""
    if intent:
        candidates = rule.intent_skill_candidates(intent, instance.language) if rule else ()
        if not attribute:
            attribute = rule.intent_default_attribute(intent) if rule else ""
    else:
        for intent_name, aliases, skill_candidates, attr_key in _fallback_intent_specs(instance.language):
            if any(_normalized(alias) in text for alias in aliases):
                intent = intent_name
                candidates = skill_candidates
                if not attribute:
                    attribute = attr_key
                break

    direct_skill = _find_skill(character_sheet, text, ())
    skill = selected_skill or direct_skill
    if not skill and candidates:
        skill = _find_skill(character_sheet, text, candidates)

    explicit_check = bool(selected_skill or selected_attribute)
    # 通用检定词：优先用规则词表的 generic 意图（整词边界，避免 'roll' 命中
    # 'scroll'）；规则没词表时回退全局兜底词（按语言子串）。
    generic_check = False
    if not explicit_check:
        if rule and "generic" in rule.intents:
            generic_check = rule.find_intent(
                action.get("text"), instance.language, dice_system
            ) == "generic"
        else:
            generic_check = any(word in text for word in _fallback_generic_words(instance.language))
    if not (explicit_check or intent or direct_skill or generic_check):
        return None

    if attribute and rule and attribute not in rule.attribute_keys:
        attribute = "int" if "int" in rule.attribute_keys else (rule.attribute_keys[0] if rule.attribute_keys else "")
    if not attribute:
        attribute = "dex" if not rule or "dex" in rule.attribute_keys else (rule.attribute_keys[0] if rule.attribute_keys else "")

    subject = skill or _attribute_name(rule, attribute)
    label = localized_text(instance.language, {
        "en": f"{subject} Check",
        "zh-CN": f"{subject}检定",
        "ja": f"{subject}判定",
    })
    advantage_mode, advantage_note = detect_advantage_mode(text, action, rule)
    actor_name = str(instance.players.get(uid, {}).get("character_name") or uid)
    return {
        "check_id": uuid.uuid4().hex,
        "required": True,
        "actor_uid": uid,
        "actor_name": actor_name,
        "dice_system": "d100" if dice_system == "d100" else "d20",
        "label": label,
        "intent": intent or "generic",
        "skill": skill,
        "attribute": attribute,
        "advantage_mode": advantage_mode,
        "advantage_note": advantage_note or None,
    }


def _effective_advantage_mode(request: dict[str, Any], rule: RuleSystem | None) -> str:
    mode = str(request.get("advantage_mode") or "")
    if rule is not None and mode and not rule.supports_advantage_mode(mode):
        return ""
    return mode if mode in {"advantage", "disadvantage"} else ""


def roll_check_request(request: dict[str, Any], rule: RuleSystem | None = None) -> dict[str, Any]:
    """按 CheckRequest 只生成原始骰值；规则修正与成败由判定解析器计算。"""
    dice_system = str(request.get("dice_system") or "").lower()
    mode = _effective_advantage_mode(request, rule)
    if dice_system == "d100":
        if mode == "advantage":
            result, _ = check_d100_bonus(50, bonus_dice=1)
            rolls = list(result.rolls)
            value = result.natural
        elif mode == "disadvantage":
            result, _ = check_d100_bonus(50, penalty_dice=1)
            rolls = list(result.rolls)
            value = result.natural
        else:
            result = roll("d100")
            rolls = [result.natural]
            value = result.natural
    elif dice_system == "d20":
        if mode in {"advantage", "disadvantage"}:
            rolls = [roll("d20").natural, roll("d20").natural]
            value = max(rolls) if mode == "advantage" else min(rolls)
        else:
            result = roll("d20")
            rolls = [result.natural]
            value = result.natural
    else:
        raise ValueError(f"不支持的检定骰制: {dice_system}")
    if dice_system == "d20":
        crit_on, fumble_on = d20_critical_thresholds(rule)
        critical = crit_on is not None and crit_on <= value <= 20
        fumble = fumble_on is not None and 1 <= value <= fumble_on
    else:
        target = request.get("target")
        if target is None:
            critical = value == 1
            fumble = value == 100
        else:
            verdict = coc_success_level(value, max(1, min(99, int(target))))
            critical = verdict == "大成功"
            fumble = verdict == "大失败"
    return {
        "ok": True,
        "check_id": str(request.get("check_id") or ""),
        "dice_system": dice_system,
        "value": value,
        "rolls": rolls,
        "critical": critical,
        "fumble": fumble,
    }


def _skill_row(skill: object) -> dict[str, Any] | None:
    if isinstance(skill, dict):
        name = str(skill.get("name") or "").strip()
        if name:
            return {"name": name, "value": int(skill.get("value", 20) or 20)}
    elif isinstance(skill, str) and skill.strip():
        return {"name": skill.strip(), "value": 20}
    return None


def _resolve_skill(character_sheet: dict, requested_name: str, text: str) -> dict[str, Any] | None:
    rows = [row for item in (character_sheet.get("skills") or []) if (row := _skill_row(item))]
    if requested_name:
        exact = next((row for row in rows if row["name"] == requested_name), None)
        if exact:
            return exact
    matches = [row for row in rows if row["name"] and row["name"] in text]
    return max(matches, key=lambda row: int(row["value"])) if matches else None


def _attribute_label(rule: RuleSystem | None, key: str) -> str:
    if rule:
        for attribute in rule.attributes:
            if attribute.get("key") == key:
                return str(attribute.get("name") or key)
    return key


def default_check_attribute(text: str, rule: RuleSystem | None) -> str:
    if rule:
        intent = rule.find_intent(text, "")
        if intent:
            candidate = rule.intent_default_attribute(intent)
            if candidate in rule.attribute_keys:
                return candidate
        if "dex" in rule.attribute_keys:
            return "dex"
        if rule.attribute_keys:
            return rule.attribute_keys[0]
    return "dex"


def _bounded_modifier(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(-20, min(20, parsed))


def resolve_check_request(
    instance: GameInstance,
    action: dict[str, Any],
    rule: RuleSystem | None,
) -> dict[str, Any] | None:
    """结算一个已经掷骰的请求，返回唯一的结构化判定结果。

    本函数是 d20 总值/DC 与 CoC 成功等级的权威入口；命令层只负责记录结果
    和生成给 GM 的说明文本，不再自行重复规则数学。
    """
    request = action.get("check_request") if isinstance(action.get("check_request"), dict) else {}
    uid = str(action.get("user_id") or request.get("actor_uid") or "")
    if uid not in instance.players:
        return None
    try:
        roll_value = int(action.get("dice_value") or 0)
    except (TypeError, ValueError):
        return None
    if roll_value <= 0:
        return None

    dice_system = str(request.get("dice_system") or (rule.dice_system if rule else "d20")).lower()
    maximum = 100 if dice_system == "d100" else 20
    if dice_system not in {"d20", "d100"} or not 1 <= roll_value <= maximum:
        raise ValueError(f"非法的 {dice_system} 检定值: {roll_value}")
    raw_rolls = action.get("dice_rolls")
    rolls = [int(value) for value in raw_rolls] if isinstance(raw_rolls, list) and raw_rolls else [roll_value]
    if any(value < 1 or value > maximum for value in rolls):
        raise ValueError(f"非法的 {dice_system} 候选骰值: {rolls}")
    advantage_mode = _effective_advantage_mode(request, rule)
    if advantage_mode:
        if len(rolls) < 2:
            raise ValueError(f"{advantage_mode} 检定缺少候选骰值")
        if dice_system == "d100":
            expected = min(rolls) if advantage_mode == "advantage" else max(rolls)
        else:
            expected = max(rolls) if advantage_mode == "advantage" else min(rolls)
        if roll_value != expected:
            raise ValueError(f"{advantage_mode} 检定取值错误: {roll_value} != {expected}")
    elif roll_value not in rolls:
        raise ValueError(f"检定值 {roll_value} 不在候选骰值 {rolls} 中")

    text = str(action.get("text") or "")
    character_sheet = instance.get_character_sheet(uid)
    attributes = character_sheet.get("attributes") if isinstance(character_sheet.get("attributes"), dict) else {}
    requested_skill = str(request.get("skill") or action.get("selected_skill") or "")
    matched_skill = _resolve_skill(character_sheet, requested_skill, text)
    skill_name = str(matched_skill.get("name") or "") if matched_skill else ""
    actor_name = str(instance.players.get(uid, {}).get("character_name") or uid)
    common = {
        "check_id": str(request.get("check_id") or ""),
        "label": str(request.get("label") or ""),
        "actor_uid": uid,
        "actor_name": actor_name,
        "dice": dice_system,
        "skill": skill_name,
        "roll": roll_value,
        "rolls": rolls,
        "advantage_mode": advantage_mode,
        "advantage_note": str(request.get("advantage_note") or "") or None,
        "kind": str(request.get("kind") or "check"),
        "opponent": str(request.get("opponent") or ""),
        "assist": list(request.get("assist") or []),
        "planner_source": str(request.get("planner_source") or "legacy"),
    }

    if dice_system == "d100":
        if matched_skill:
            threshold = int(matched_skill.get("value", 20) or 20)
            attribute_key = ""
        else:
            attribute_key = str(request.get("attribute") or action.get("selected_attribute") or "int")
            raw_value = int(attributes.get(attribute_key, 10) or 10)
            # CoC 新卡属性本身是百分制；兼容旧卡 3-18 属性并自动换算为百分制。
            threshold = raw_value if raw_value > 20 else raw_value * 5
        threshold = max(1, min(99, threshold + _bounded_modifier(request.get("circumstance_modifier"))))
        verdict = coc_success_level(roll_value, threshold)
        luck = int(character_sheet.get("luck", 0) or 0)
        luck_cost = roll_value - threshold if verdict == "失败" else 0
        common.update({
            "label": common["label"] or f"{skill_name or _attribute_label(rule, attribute_key)}检定",
            "attribute": _attribute_label(rule, attribute_key) if attribute_key else None,
            "threshold": threshold,
            "hard_threshold": threshold // 2,
            "extreme_threshold": threshold // 5,
            "verdict": verdict,
            "luck_spend_available": 0 < luck_cost <= luck,
            "luck_cost": luck_cost if 0 < luck_cost <= luck else None,
            "is_critical": verdict == "大成功",
            "is_fumble": verdict == "大失败",
        })
        return common

    attribute_key = str(request.get("attribute") or action.get("selected_attribute") or "")
    if not attribute_key:
        attribute_key = default_check_attribute(text, rule)
    attribute_value = int(attributes.get(attribute_key, 10) or 10)
    attribute_modifier = rule.attribute_modifier(attribute_value) if rule else (attribute_value - 10) // 2
    skill_value = int(matched_skill.get("value", 0) or 0) if matched_skill else 0
    skill_bonus = 0
    bonus_label = ""
    if rule and rule.skill_mode == "proficiency" and matched_skill:
        skill_bonus = rule.proficiency_bonus(int(character_sheet.get("level", 1) or 1))
        bonus_label = f"熟练加值 +{skill_bonus}"
    elif rule and matched_skill:
        skill_bonus = rule.skill_bonus(skill_value)
        bonus_label = f"技能「{skill_name}」{skill_value} → 加值 +{skill_bonus}"
    circumstance_modifier = _bounded_modifier(request.get("circumstance_modifier"))
    modifier = attribute_modifier + skill_bonus + circumstance_modifier
    total = roll_value + modifier
    try:
        raw_dc = int(request["target"]) if request.get("target") is not None else (
            rule.dc_for_difficulty(instance.difficulty, "normal") if rule else 10
        )
    except (TypeError, ValueError):
        raw_dc = rule.dc_for_difficulty(instance.difficulty, "normal") if rule else 10
    dc = max(1, min(d20_dc_cap(rule), raw_dc))

    opponent_ref = str(request.get("opponent") or "")
    opponent_name = ""
    opponent_roll = request.get("opponent_roll")
    opponent_modifier = _bounded_modifier(request.get("opponent_modifier"))
    opponent_total = request.get("opponent_total")
    if opponent_ref:
        opponent_attributes: dict[str, Any] = {}
        if opponent_ref.startswith("npc:"):
            npc_id = opponent_ref.split(":", 1)[1]
            npc = instance.npcs.get(npc_id, {})
            opponent_name = str(npc.get("name") or npc.get("character_name") or npc_id)
            opponent_attributes = npc.get("attributes") if isinstance(npc.get("attributes"), dict) else {}
        elif opponent_ref in instance.players:
            opponent_name = str(instance.players[opponent_ref].get("character_name") or opponent_ref)
            sheet = instance.get_character_sheet(opponent_ref)
            opponent_attributes = sheet.get("attributes") if isinstance(sheet.get("attributes"), dict) else {}
        if opponent_name:
            if opponent_roll is None or opponent_total is None:
                opponent_value = int(opponent_attributes.get(attribute_key, 10) or 10)
                opponent_modifier = rule.attribute_modifier(opponent_value) if rule else (opponent_value - 10) // 2
                opponent_roll = roll("d20").natural
                opponent_total = int(opponent_roll) + opponent_modifier
                # 缓存对抗结果，保证同一请求重试时不会偷偷重掷对手骰。
                request["opponent_roll"] = opponent_roll
                request["opponent_modifier"] = opponent_modifier
                request["opponent_total"] = opponent_total
            dc = max(1, min(d20_dc_cap(rule), int(opponent_total)))

    critical_on, fumble_on = d20_critical_thresholds(rule)
    verdict = d20_verdict(
        roll_value,
        total,
        dc,
        crit_on=critical_on,
        fumble_on=fumble_on,
    )
    attribute_label = _attribute_label(rule, attribute_key)
    common.update({
        "label": common["label"] or f"{skill_name or attribute_label}检定",
        "attribute": attribute_label,
        "modifier": modifier,
        "modifier_breakdown": "；".join(filter(None, [
            bonus_label,
            f"情境修正 {circumstance_modifier:+d}" if circumstance_modifier else "",
        ])) or None,
        "total": total,
        "dc": dc,
        "difficulty": instance.difficulty,
        "opponent_name": opponent_name,
        "opponent_roll": opponent_roll,
        "opponent_modifier": opponent_modifier if opponent_name else None,
        "opponent_total": opponent_total,
        "verdict": verdict,
        "is_critical": verdict == "大成功",
        "is_fumble": verdict == "大失败",
    })
    return common
