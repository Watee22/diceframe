"""d20 规则层：借鉴 D&D 优势/劣势机制的娱乐房规 + DC 硬上限。

注意：标准 D&D 5e 属性检定并没有自然 20/1 自动成功/失败（自动命中/失手
主要属于攻击检定）。本产品将自然 20/1 保留为娱乐暴击通道，不作严格
D&D 规则宣传。
"""

from __future__ import annotations

import random

from src.engine.dice_rng import DiceResult, roll


def d20_dc_cap(rule: object) -> int:
    """d20 情境 DC 的硬上限：规则 dc_table 最高档 + 5，默认 20。

    防止 AI 裁判后期报出 25–30 的失控 DC 导致“只有自然 20 才成功”。
    """
    table = getattr(rule, "dc_table", None) if rule is not None else None
    values = [int(v) for v in table.values() if isinstance(v, (int, float))] if isinstance(table, dict) else []
    return (max(values) if values else 15) + 5


def check_d20(modifier: int = 0, dc: int = 10, crit_on: int = 20, fumble_on: int = 1) -> tuple[DiceResult, str]:
    """d20 属性检定，返回 (结果, "成功"/"失败"/"大成功"/"大失败")。

    娱乐化房规：自然 20/1 走大成功/大失败通道（见模块 docstring）。

    Args:
        modifier: 属性修正值
        dc: 难度等级 (Difficulty Class)
        crit_on: 大成功阈值（默认 20，轻松模式可降为 19）
        fumble_on: 大失败阈值（默认 1，硬核模式可升为 2）
    """
    result = roll(f"d20{modifier:+d}" if modifier else "d20")
    if crit_on <= result.natural <= 20:
        result.is_critical = True
        return result, "大成功"
    if 1 <= result.natural <= fumble_on:
        result.is_fumble = True
        return result, "大失败"
    return result, "成功" if result.total >= dc else "失败"


def check_d20_advantage(
    modifier: int = 0,
    dc: int = 10,
    *,
    advantage: bool = False,
    disadvantage: bool = False,
    crit_on: int = 20,
    fumble_on: int = 1,
) -> tuple[DiceResult, str]:
    """d20 优势/劣势检定（借鉴 D&D 优势/劣势机制的娱乐房规）。

    优势：掷 2 个 d20 取高；劣势：掷 2 个 d20 取低。
    同时存在优势和劣势时互相抵消，退回普通 d20 检定。
    """
    if advantage and disadvantage:
        return check_d20(modifier=modifier, dc=dc, crit_on=crit_on, fumble_on=fumble_on)
    if not advantage and not disadvantage:
        return check_d20(modifier=modifier, dc=dc, crit_on=crit_on, fumble_on=fumble_on)

    rolls = [random.randint(1, 20), random.randint(1, 20)]
    natural = max(rolls) if advantage else min(rolls)
    total = natural + modifier
    mode = "kh1" if advantage else "kl1"
    result = DiceResult(
        formula=f"2d20{mode}{modifier:+d}" if modifier else f"2d20{mode}",
        rolls=rolls,
        modifier=modifier,
        total=total,
        natural=natural,
        is_critical=crit_on <= natural <= 20,
        is_fumble=1 <= natural <= fumble_on,
    )
    if result.is_critical:
        return result, "大成功"
    if result.is_fumble:
        return result, "大失败"
    return result, "成功" if total >= dc else "失败"
