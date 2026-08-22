"""Simulate long campaigns and independently verify every dice result."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.commands.dice_resolver import DiceResolver  # noqa: E402
from src.engine.checks import build_check_request, roll_check_request  # noqa: E402
from src.engine.dice import roll  # noqa: E402
from src.engine.game_instance import GameInstance  # noqa: E402
from src.rules.rule_system import RuleSystem  # noqa: E402


@dataclass
class AuditResult:
    name: str
    dice_system: str
    actions: int = 0
    checks: int = 0
    verdicts: Counter[str] = field(default_factory=Counter)
    error_count: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    def expect(self, condition: bool, message: str) -> None:
        if condition:
            return
        self.error_count += 1
        if len(self.errors) < 20:
            self.errors.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dice_system": self.dice_system,
            "actions": self.actions,
            "checks": self.checks,
            "verdicts": dict(sorted(self.verdicts.items())),
            "error_count": self.error_count,
            "errors": self.errors,
            "details": self.details,
        }


_ACTION_SENTENCES = (
    "我抬肩撞向锈蚀的铁门。",
    "我贴着阴影绕过巡逻者。",
    "我检查墙上的符号寻找规律。",
    "我观察四周寻找隐藏的危险。",
    "我稳住呼吸说服守卫放行。",
    "我护住队友穿过正在坍塌的走廊。",
)

_DND_ACTION_SCENARIOS = (
    {"attribute": "str", "attribute_value": 16, "base_dc": 12, "text": "我抬肩撞向锈蚀的铁门。"},
    {"attribute": "dex", "attribute_value": 16, "base_dc": 14, "text": "我贴着阴影绕过巡逻者。"},
    {"attribute": "int", "attribute_value": 15, "base_dc": 15, "text": "我检查墙上的符号寻找规律。"},
    {"attribute": "wis", "attribute_value": 14, "base_dc": 13, "text": "我观察四周寻找隐藏的危险。"},
    {"attribute": "cha", "attribute_value": 16, "base_dc": 15, "text": "我稳住呼吸说服守卫放行。"},
    {"attribute": "con", "attribute_value": 14, "base_dc": 16, "text": "我护住队友穿过正在坍塌的走廊。"},
)


def _action_text(round_index: int, player_index: int) -> str:
    sentence = _ACTION_SENTENCES[player_index % len(_ACTION_SENTENCES)]
    return f"第{round_index}轮，{sentence}"


def _dnd_action(round_index: int, player_index: int) -> tuple[str, str, int, int]:
    scenario = _DND_ACTION_SCENARIOS[player_index % len(_DND_ACTION_SCENARIOS)]
    dc_adjustments = (-2, 0, 0, 1, 2)
    requested_dc = int(scenario["base_dc"]) + dc_adjustments[(round_index - 1) % len(dc_adjustments)]
    return (
        f"第{round_index}轮，{scenario['text']}",
        str(scenario["attribute"]),
        int(scenario["attribute_value"]),
        requested_dc,
    )


def _expected_coc(roll_value: int, threshold: int) -> str:
    if roll_value == 1:
        return "大成功"
    if roll_value == 100 or (threshold < 50 and roll_value >= 96):
        return "大失败"
    if roll_value > threshold:
        return "失败"
    if roll_value <= threshold // 5:
        return "极难成功"
    if roll_value <= threshold // 2:
        return "困难成功"
    return "普通成功"


def _critical_thresholds(rule: RuleSystem) -> tuple[int | None, int | None]:
    critical = rule.check_mechanic.get("critical")
    if not isinstance(critical, dict):
        return 20, 1

    def read(name: str) -> int | None:
        raw = critical.get(name)
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if 1 <= value <= 20 else None

    return read("success"), read("failure")


def _expected_d20(
    natural: int,
    total: int,
    dc: int,
    crit_on: int | None,
    fumble_on: int | None,
) -> str:
    if crit_on is not None and natural >= crit_on:
        return "大成功"
    if fumble_on is not None and natural <= fumble_on:
        return "大失败"
    return "成功" if total >= dc else "失败"


def _dc_cap(rule: RuleSystem) -> int:
    try:
        value = int(rule.template.get("max_check_dc", 20))
    except (TypeError, ValueError):
        value = 20
    return max(1, min(40, value))


def _attribute_bounds(rule: RuleSystem, attribute: str) -> tuple[int, int]:
    definition = next(
        (item for item in rule.attributes if str(item.get("key") or "") == attribute),
        {},
    )
    return int(definition.get("min", 3)), int(definition.get("max", 20))


def _make_instance(rule: RuleSystem, attribute: str, players_per_round: int) -> GameInstance:
    instance = GameInstance(("audit", rule.rule_id, "dice"), rule_id=rule.rule_id)
    base_attributes = {key: 10 for key in rule.attribute_keys} or {attribute: 10}
    for player_index in range(players_per_round):
        uid = f"p{player_index + 1}"
        instance.players[uid] = {
            "character_name": f"审计角色{player_index + 1}",
            "character_sheet": {
                "attributes": dict(base_attributes),
                "skills": [],
                "luck": 0,
            },
        }
    return instance


def _simulate_d20(
    rule: RuleSystem,
    rounds: int,
    players_per_round: int,
    selector: random.Random,
    capture_details: bool,
) -> AuditResult:
    result = AuditResult(rule.rule_id, "d20")
    resolver = DiceResolver()
    attribute = rule.attribute_keys[0] if rule.attribute_keys else "dex"
    minimum, maximum = _attribute_bounds(rule, attribute)
    instance = _make_instance(rule, attribute, players_per_round)
    crit_on, fumble_on = _critical_thresholds(rule)
    cap = _dc_cap(rule)
    modes = ("", "advantage", "disadvantage")

    for round_index in range(1, rounds + 1):
        instance.round_number = round_index
        instance.reset_round_checks()
        for player_index in range(players_per_round):
            action_index = (round_index - 1) * players_per_round + player_index + 1
            uid = f"p{player_index + 1}"
            if rule.rule_id == "dnd5e":
                action_text, action_attribute, attr_value, requested_dc = _dnd_action(
                    round_index,
                    player_index,
                )
                circumstance = 0
            else:
                action_text = _action_text(round_index, player_index)
                action_attribute = attribute
                attr_value = selector.randint(minimum, maximum)
                circumstance = (action_index % 11) - 5
                requested_dc = 1 + ((action_index * 17) % 45)
            mode = modes[(round_index + player_index - 1) % len(modes)]
            effective_mode = mode if rule.supports_advantage_mode(mode) else ""
            advantage_note = {
                "advantage": "队友提供协助",
                "disadvantage": "环境造成干扰",
            }.get(mode, "")
            instance.players[uid]["character_sheet"]["attributes"][action_attribute] = attr_value
            request = {
                "actor_uid": uid,
                "dice_system": "d20",
                "attribute": action_attribute,
                "target": requested_dc,
                "circumstance_modifier": circumstance,
                "advantage_mode": mode,
                "advantage_note": advantage_note,
            }
            rolled = roll_check_request(request, rule)
            action = {
                "user_id": uid,
                "text": action_text,
                "check_request": request,
                "dice_value": rolled["value"],
                "dice_rolls": rolled["rolls"],
            }
            resolver.resolve_action_check(instance, action, rule)
            check = instance.last_check or {}
            natural = int(rolled["value"])
            modifier = (attr_value - 10) // 2 + circumstance
            dc = max(1, min(cap, requested_dc))
            total = natural + modifier
            verdict = _expected_d20(natural, total, dc, crit_on, fumble_on)
            expected_critical = verdict == "大成功"
            expected_fumble = verdict == "大失败"

            result.actions += 1
            result.checks += 1
            result.verdicts[verdict] += 1
            prefix = f"round={round_index} player={uid} roll={rolled['rolls']}"
            result.expect(1 <= natural <= 20, f"{prefix}: natural 越界: {natural}")
            result.expect(check.get("roll") == natural, f"{prefix}: 最终骰值不一致")
            result.expect(check.get("modifier") == modifier, f"{prefix}: 修正值不一致")
            result.expect(check.get("total") == total, f"{prefix}: 总值不一致")
            result.expect(check.get("dc") == dc, f"{prefix}: DC 未正确钳制")
            result.expect(check.get("verdict") == verdict, f"{prefix}: 判定结果不一致")
            result.expect(
                check.get("advantage_mode") == effective_mode,
                f"{prefix}: 规则能力与实际优势模式不一致",
            )
            if effective_mode == "advantage":
                result.expect(
                    len(rolled["rolls"]) == 2 and natural == max(rolled["rolls"]),
                    f"{prefix}: 优势未正确取高",
                )
            elif effective_mode == "disadvantage":
                result.expect(
                    len(rolled["rolls"]) == 2 and natural == min(rolled["rolls"]),
                    f"{prefix}: 劣势未正确取低",
                )
            else:
                result.expect(len(rolled["rolls"]) == 1, f"{prefix}: 普通检定不应掷多颗 d20")
            result.expect(rolled["critical"] is expected_critical, f"{prefix}: 预掷大成功标记不一致")
            result.expect(rolled["fumble"] is expected_fumble, f"{prefix}: 预掷大失败标记不一致")
            if capture_details:
                result.details.append({
                    "round": round_index,
                    "player": uid,
                    "action": action_text,
                    "attribute": action_attribute,
                    "attribute_value": attr_value,
                    "requested_dc": requested_dc,
                    "dc": dc,
                    "circumstance_modifier": circumstance,
                    "requested_advantage_mode": mode or "normal",
                    "advantage_mode": effective_mode or "normal",
                    "advantage_note": advantage_note or None,
                    "rolls": rolled["rolls"],
                    "natural": natural,
                    "modifier": modifier,
                    "total": total,
                    "verdict": verdict,
                    "independently_verified": check.get("verdict") == verdict,
                })
        result.expect(
            len(instance.last_checks) == players_per_round,
            f"round={round_index}: 本轮检定数不是 {players_per_round}",
        )

    return result


def _simulate_d100(
    rule: RuleSystem,
    rounds: int,
    players_per_round: int,
    capture_details: bool,
) -> AuditResult:
    result = AuditResult(rule.rule_id, "d100")
    resolver = DiceResolver()
    attribute = rule.attribute_keys[0] if rule.attribute_keys else "focus"
    instance = _make_instance(rule, attribute, players_per_round)
    modes = ("", "advantage", "disadvantage")

    for round_index in range(1, rounds + 1):
        instance.round_number = round_index
        instance.reset_round_checks()
        for player_index in range(players_per_round):
            action_index = (round_index - 1) * players_per_round + player_index + 1
            uid = f"p{player_index + 1}"
            action_text = _action_text(round_index, player_index)
            skill_value = 1 + ((action_index * 37) % 99)
            circumstance = (action_index % 9) - 4
            threshold = max(1, min(99, skill_value + circumstance))
            requested_mode = modes[(round_index + player_index - 1) % len(modes)]
            effective_mode = requested_mode if rule.supports_advantage_mode(requested_mode) else ""
            instance.players[uid]["character_sheet"]["skills"] = [
                {"name": "审计技能", "value": skill_value},
            ]
            request = {
                "actor_uid": uid,
                "dice_system": "d100",
                "attribute": attribute,
                "skill": "审计技能",
                "target": threshold,
                "circumstance_modifier": circumstance,
                "advantage_mode": requested_mode,
            }
            rolled = roll_check_request(request, rule)
            action = {
                "user_id": uid,
                "text": action_text,
                "check_request": request,
                "dice_value": rolled["value"],
                "dice_rolls": rolled["rolls"],
            }
            resolver.resolve_action_check(instance, action, rule)
            check = instance.last_check or {}
            natural = int(rolled["value"])
            verdict = _expected_coc(natural, threshold)

            result.actions += 1
            result.checks += 1
            result.verdicts[verdict] += 1
            prefix = f"round={round_index} player={uid} roll={natural} skill={skill_value}"
            result.expect(1 <= natural <= 100, f"{prefix}: d100 越界")
            result.expect(check.get("roll") == natural, f"{prefix}: 最终骰值不一致")
            result.expect(check.get("threshold") == threshold, f"{prefix}: 技能阈值不一致")
            result.expect(check.get("verdict") == verdict, f"{prefix}: CoC 判定不一致")
            result.expect(
                check.get("advantage_mode") == effective_mode,
                f"{prefix}: 规则能力与实际奖惩骰模式不一致",
            )
            if effective_mode == "advantage":
                result.expect(
                    len(rolled["rolls"]) == 2 and natural == min(rolled["rolls"]),
                    f"{prefix}: CoC 奖励骰未按最终值取低",
                )
            elif effective_mode == "disadvantage":
                result.expect(
                    len(rolled["rolls"]) == 2 and natural == max(rolled["rolls"]),
                    f"{prefix}: CoC 惩罚骰未按最终值取高",
                )
            else:
                result.expect(len(rolled["rolls"]) == 1, f"{prefix}: 普通 d100 不应产生多个候选值")
            result.expect(rolled["critical"] is (verdict == "大成功"), f"{prefix}: 预掷大成功标记不一致")
            result.expect(rolled["fumble"] is (verdict == "大失败"), f"{prefix}: 预掷大失败标记不一致")
            if capture_details:
                result.details.append({
                    "round": round_index,
                    "player": uid,
                    "action": action_text,
                    "attribute": attribute,
                    "skill": "审计技能",
                    "skill_value": skill_value,
                    "circumstance_modifier": circumstance,
                    "requested_advantage_mode": requested_mode or "normal",
                    "advantage_mode": effective_mode or "normal",
                    "threshold": threshold,
                    "roll": natural,
                    "verdict": verdict,
                    "independently_verified": check.get("verdict") == verdict,
                })
        result.expect(
            len(instance.last_checks) == players_per_round,
            f"round={round_index}: 本轮检定数不是 {players_per_round}",
        )
    return result


def _simulate_none(
    rule: RuleSystem,
    rounds: int,
    players_per_round: int,
    capture_details: bool,
) -> AuditResult:
    result = AuditResult(rule.rule_id, "none")
    attribute = rule.attribute_keys[0] if rule.attribute_keys else "dex"
    instance = _make_instance(rule, attribute, players_per_round)
    for round_index in range(1, rounds + 1):
        for player_index in range(players_per_round):
            uid = f"p{player_index + 1}"
            action_text = _action_text(round_index, player_index)
            request = build_check_request(
                instance,
                {
                    "user_id": uid,
                    "text": action_text,
                    "selected_attribute": attribute,
                },
                rule,
            )
            result.actions += 1
            result.expect(request is None, f"round={round_index} player={uid}: none 规则产生了检定")
            if capture_details:
                result.details.append({
                    "round": round_index,
                    "player": uid,
                    "action": action_text,
                    "roll_required": False,
                    "independently_verified": request is None,
                })
    return result


def _formula_audit(
    samples: int,
    allowed_formulas: set[str] | None = None,
) -> list[dict[str, Any]]:
    formulas = (
        ("d4", 1, 4, 0),
        ("d6", 1, 6, 0),
        ("d8", 1, 8, 0),
        ("d10", 1, 10, 0),
        ("d12", 1, 12, 0),
        ("d20", 1, 20, 0),
        ("d100", 1, 100, 0),
        ("2d6+3", 2, 6, 3),
        ("3d8-2", 3, 8, -2),
    )
    reports: list[dict[str, Any]] = []
    for formula, count, sides, modifier in formulas:
        if allowed_formulas is not None and formula not in allowed_formulas:
            continue
        errors = 0
        observed_min: int | None = None
        observed_max: int | None = None
        for _ in range(samples):
            result = roll(formula)
            observed_min = result.total if observed_min is None else min(observed_min, result.total)
            observed_max = result.total if observed_max is None else max(observed_max, result.total)
            errors += int(len(result.rolls) != count)
            errors += int(any(value < 1 or value > sides for value in result.rolls))
            errors += int(result.natural != sum(result.rolls))
            errors += int(result.total != sum(result.rolls) + modifier)
        reports.append({
            "formula": formula,
            "samples": samples,
            "observed_min": observed_min,
            "observed_max": observed_max,
            "error_count": errors,
        })
    return reports


def _distribution_audit(sides: int, samples: int) -> dict[str, Any]:
    counts = Counter(roll(f"d{sides}").natural for _ in range(samples))
    expected = samples / sides
    probability = 1 / sides
    standard_deviation = math.sqrt(samples * probability * (1 - probability))
    chi_square = sum((counts[face] - expected) ** 2 / expected for face in range(1, sides + 1))
    degrees = sides - 1
    chi_limit = degrees + 6 * math.sqrt(2 * degrees)
    max_z = max(abs(counts[face] - expected) / standard_deviation for face in range(1, sides + 1))
    mean = sum(face * count for face, count in counts.items()) / samples
    return {
        "dice": f"d{sides}",
        "samples": samples,
        "mean": round(mean, 6),
        "expected_mean": (sides + 1) / 2,
        "min_count": min(counts.values()),
        "max_count": max(counts.values()),
        "max_z": round(max_z, 4),
        "chi_square": round(chi_square, 4),
        "chi_limit": round(chi_limit, 4),
        "ok": max_z <= 6 and chi_square <= chi_limit,
    }


def _extra_rule_files(paths: list[Path] | None) -> list[Path]:
    files: set[Path] = set()
    for raw_path in paths or []:
        path = raw_path.resolve()
        if path.is_file() and path.suffix.lower() == ".json":
            files.add(path)
            continue
        if not path.is_dir():
            raise ValueError(f"规则路径不存在: {path}")
        if (path / "plugin.json").is_file():
            files.update((path / "content" / "rules").glob("*.json"))
        if path.name == "rules":
            files.update(path.glob("*.json"))
        files.update(path.glob("content/rules/*.json"))
        files.update(path.glob("*/content/rules/*.json"))
    return sorted(item.resolve() for item in files if item.is_file())


def _scenarios(rule_paths: list[Path] | None = None) -> list[RuleSystem]:
    builtins = [
        "dnd5e.json",
        "freeform_fantasy.json",
        "freeform_cyberpunk.json",
        "freeform_wuxia.json",
        "freeform_coc.json",
        "tavern_free.json",
    ]
    rules = [RuleSystem.load(ROOT / "templates" / "rules" / name) for name in builtins]
    rules.extend([
        RuleSystem({
            "rule_id": "audit_strict_d20",
            "rule_name": "严格总值 d20",
            "dice_system": "d20",
            "max_check_dc": 30,
            "attributes": [{"key": "focus", "name": "专注", "min": 3, "max": 20}],
            "check_mechanic": {
                "dice": "d20",
                "comparison": "roll_plus_modifier_gte_target",
                "critical": {},
            },
        }),
        RuleSystem({
            "rule_id": "audit_cinematic_d20",
            "rule_name": "电影化 d20",
            "dice_system": "d20",
            "max_check_dc": 18,
            "attributes": [{"key": "style", "name": "气势", "min": 3, "max": 18}],
            "check_mechanic": {
                "dice": "d20",
                "comparison": "roll_plus_modifier_gte_target",
                "critical": {"success": 19, "failure": 2},
            },
        }),
        RuleSystem({
            "rule_id": "audit_custom_d100",
            "rule_name": "自定义百分制",
            "dice_system": "d100",
            "attributes": [{"key": "focus", "name": "专注", "min": 1, "max": 99}],
        }),
    ])
    rules.extend(RuleSystem.load(path) for path in _extra_rule_files(rule_paths))
    return rules


def run_audit(
    *,
    rounds_per_rule: int = 10_000,
    distribution_samples: int = 200_000,
    seed: int = 20260822,
    players_per_round: int = 1,
    rule_ids: set[str] | None = None,
    rule_paths: list[Path] | None = None,
    capture_details: bool = False,
) -> dict[str, Any]:
    if rounds_per_rule < 1:
        raise ValueError("rounds_per_rule 必须大于 0")
    if distribution_samples < 1_000:
        raise ValueError("distribution_samples 必须至少为 1000")
    if not 1 <= players_per_round <= 6:
        raise ValueError("players_per_round 必须在 1 到 6 之间")

    random.seed(seed)
    selector = random.Random(seed ^ 0xD1CE)
    scenario_results: list[AuditResult] = []
    available_rules = _scenarios(rule_paths)
    selected_rules = [rule for rule in available_rules if rule_ids is None or rule.rule_id in rule_ids]
    if rule_ids:
        missing = rule_ids - {rule.rule_id for rule in selected_rules}
        if missing:
            raise ValueError(f"未知规则: {', '.join(sorted(missing))}")
    for rule in selected_rules:
        if rule.dice_system == "d20":
            scenario_results.append(_simulate_d20(
                rule,
                rounds_per_rule,
                players_per_round,
                selector,
                capture_details,
            ))
        elif rule.dice_system == "d100":
            scenario_results.append(_simulate_d100(
                rule,
                rounds_per_rule,
                players_per_round,
                capture_details,
            ))
        else:
            scenario_results.append(_simulate_none(
                rule,
                rounds_per_rule,
                players_per_round,
                capture_details,
            ))

    formula_samples = max(1_000, min(rounds_per_rule, 10_000))
    allowed_formulas = None if rule_ids is None else {
        rule.dice_system for rule in selected_rules if rule.dice_system in {"d20", "d100"}
    }
    formula_reports = _formula_audit(formula_samples, allowed_formulas)
    random.seed(seed ^ 0xB1A5)
    distribution_sides = [20, 100]
    if rule_ids is not None:
        distribution_sides = [
            sides for sides, dice_system in ((20, "d20"), (100, "d100"))
            if dice_system in allowed_formulas
        ]
    distributions = [_distribution_audit(sides, distribution_samples) for sides in distribution_sides]
    scenario_error_count = sum(item.error_count for item in scenario_results)
    formula_error_count = sum(item["error_count"] for item in formula_reports)
    distribution_error_count = sum(not item["ok"] for item in distributions)
    return {
        "ok": not (scenario_error_count or formula_error_count or distribution_error_count),
        "seed": seed,
        "rounds_per_rule": rounds_per_rule,
        "players_per_round": players_per_round,
        "distribution_samples": distribution_samples,
        "total_actions": sum(item.actions for item in scenario_results),
        "total_checks": sum(item.checks for item in scenario_results),
        "scenario_error_count": scenario_error_count,
        "formula_error_count": formula_error_count,
        "distribution_error_count": distribution_error_count,
        "scenarios": [item.as_dict() for item in scenario_results],
        "formulas": formula_reports,
        "distributions": distributions,
    }


def _print_report(report: dict[str, Any]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"长团骰子审计: {status}")
    print(
        f"seed={report['seed']} rounds_per_rule={report['rounds_per_rule']} "
        f"players_per_round={report['players_per_round']} "
        f"total_actions={report['total_actions']} total_checks={report['total_checks']}"
    )
    for scenario in report["scenarios"]:
        print(
            f"- {scenario['name']}: {scenario['dice_system']} actions={scenario['actions']} "
            f"checks={scenario['checks']} "
            f"errors={scenario['error_count']} verdicts={scenario['verdicts']}"
        )
        for error in scenario["errors"]:
            print(f"  ERROR: {error}")
    for distribution in report["distributions"]:
        print(
            f"- {distribution['dice']} distribution: samples={distribution['samples']} "
            f"mean={distribution['mean']} max_z={distribution['max_z']} "
            f"chi={distribution['chi_square']}/{distribution['chi_limit']} "
            f"ok={distribution['ok']}"
        )
    print(
        f"formula_errors={report['formula_error_count']} "
        f"distribution_errors={report['distribution_error_count']}"
    )


def main() -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10_000, help="每套规则模拟回合数")
    parser.add_argument("--players", type=int, default=1, help="每回合行动的玩家数（1-6）")
    parser.add_argument("--rule", action="append", dest="rules", help="只审计指定 rule_id，可重复")
    parser.add_argument(
        "--rule-path",
        action="append",
        type=Path,
        default=[],
        help="额外模拟的规则 JSON、插件目录或内容包集合目录；可重复",
    )
    parser.add_argument("--distribution-samples", type=int, default=200_000, help="每种骰子的分布样本数")
    parser.add_argument("--seed", type=int, default=20260822, help="可复现随机种子")
    parser.add_argument("--details", action="store_true", help="在 JSON 中记录每次行动与独立复算结果")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--output", type=Path, help="将完整 JSON 报告写入文件")
    args = parser.parse_args()
    report = run_audit(
        rounds_per_rule=args.rounds,
        distribution_samples=args.distribution_samples,
        seed=args.seed,
        players_per_round=args.players,
        rule_ids=set(args.rules) if args.rules else None,
        rule_paths=args.rule_path,
        capture_details=args.details,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
