"""CoC 7e 规则层：d100 成功等级、奖励骰/惩罚骰。

只消费 dice_rng 的真实骰值；成功等级判定唯一入口为 coc_success_level，
避免同一引擎里出现两套互相矛盾的 CoC 判定。
"""

from __future__ import annotations

from src.engine.dice_rng import MAX_DICE_COUNT, DiceResult, roll, roll_die


def coc_success_level(roll_value: int, threshold: int) -> str:
    """CoC 7e 风格成功等级。"""
    if roll_value <= 1:
        return "大成功"
    if roll_value >= 100 or (threshold < 50 and roll_value >= 96):
        return "大失败"
    if roll_value > threshold:
        return "失败"
    if roll_value <= threshold // 5:
        return "极难成功"
    if roll_value <= threshold // 2:
        return "困难成功"
    return "普通成功"


def check_coc(threshold: int) -> tuple[DiceResult, str]:
    """CoC 7e 风格 d100 检定，返回成功等级。"""
    threshold = max(1, min(99, int(threshold)))
    result = roll("d100")
    verdict = coc_success_level(result.natural, threshold)
    result.is_critical = verdict == "大成功"
    result.is_fumble = verdict == "大失败"
    return result, verdict


def check_d100(threshold: int) -> tuple[DiceResult, str]:
    """d100 技能检定（掷 d100 ≤ skill 值 = 成功，用于 CoC 类规则）。

    与 coc_success_level 统一，避免同一引擎里两套互相矛盾的 CoC 判定。
    """
    return check_coc(threshold)


def check_d100_bonus(threshold: int, bonus_dice: int = 0, penalty_dice: int = 0) -> tuple[DiceResult, str]:
    """CoC 7e 奖励骰/惩罚骰。

    bonus_dice: 奖励骰数量（掷多个十位骰，取最终结果更低者）
    penalty_dice: 惩罚骰数量（掷多个十位骰，取最终结果更高者）
    """
    if bonus_dice < 0 or penalty_dice < 0:
        raise ValueError("奖励骰和惩罚骰数量不能为负数")
    if bonus_dice > MAX_DICE_COUNT or penalty_dice > MAX_DICE_COUNT:
        raise ValueError(f"奖励骰和惩罚骰数量不能超过 {MAX_DICE_COUNT}")
    if bonus_dice and penalty_dice:
        cancel_count = min(bonus_dice, penalty_dice)
        bonus_dice -= cancel_count
        penalty_dice -= cancel_count
    threshold = max(1, min(99, int(threshold)))
    units = roll_die(10, zero_based=True)
    extra_count = max(bonus_dice, penalty_dice)
    all_tens = [roll_die(10, zero_based=True) * 10 for _ in range(1 + extra_count)]
    # 先构造每个组合的最终值（00+0 = 100），再按奖惩取最高/最低；
    # 旧实现先对十位取 min/max 再转换 100，会把奖惩结果完全反转。
    candidates = [100 if (ten + units) == 0 else ten + units for ten in all_tens]
    total = max(candidates) if penalty_dice > 0 else min(candidates)
    verdict = coc_success_level(total, threshold)
    # rolls 保存所有共享个位数组合的最终候选值，便于 UI/审计证明奖惩骰
    # 确实是“同一个位 + 多个十位”，而不是简单掷两次完整 d100。
    result = DiceResult(formula="d100", rolls=candidates, modifier=0,
                        total=total, natural=total,
                        is_critical=(verdict == "大成功"), is_fumble=(verdict == "大失败"))
    return result, verdict
