"""骰子系统兼容门面 —— 实现已分层，旧导入路径保持不变。

分层结构：
- dice_rng：Dice RNG + 通用公式解析（roll / DiceResult / 防滥用上限）
- dice_rules_d20：d20 娱乐房规（check_d20 / 优势劣势 / DC 硬上限）
- dice_rules_coc：CoC 7e 规则（成功等级 / 奖惩骰）

本模块仅做再导出与玩家手动掷骰指令解析，保证
``from src.engine.dice import ...`` 的既有调用方零改动。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.engine.dice_rng import (
    MAX_DICE_COUNT,
    MAX_DICE_MODIFIER,
    MAX_DICE_SIDES,
    DiceResult,
    roll,
)
from src.engine.dice_rules_coc import (
    check_coc,
    check_d100,
    check_d100_bonus,
    coc_success_level,
)
from src.engine.dice_rules_d20 import (
    check_d20,
    check_d20_advantage,
    d20_critical_thresholds,
    d20_dc_cap,
    d20_verdict,
)

__all__ = [
    "MAX_DICE_COUNT",
    "MAX_DICE_MODIFIER",
    "MAX_DICE_SIDES",
    "DiceResult",
    "roll",
    "check_coc",
    "check_d100",
    "check_d100_bonus",
    "coc_success_level",
    "check_d20",
    "check_d20_advantage",
    "d20_critical_thresholds",
    "d20_dc_cap",
    "d20_verdict",
    "parse_player_roll",
    "InitResult",
    "roll_initiative",
]


_ROLL_COMMAND_WORDS = (
    "掷骰", "投骰", "丢骰", "骰子", "投个骰", "掷个骰", "丢个骰", "roll", "dice",
)


def parse_player_roll(text: str) -> DiceResult | None:
    """尝试从玩家文本中解析手动掷骰指令，如 /掷骰 2d6 或 roll d20+3。

    触发词覆盖中文（掷骰/投骰/丢/骰子…）与英文（roll/dice），与检定意图词表里的
    generic 别名保持一致。匹配「触发词 + 公式」结构：触发词与公式间允许空格/斜杠，
    公式需紧跟其后（防止「骰子真有趣」之类误触发——要求词后必须有 NdM 公式）。
    """
    pattern = rf"(?:{'|'.join(_ROLL_COMMAND_WORDS)})\s*[/]?\s*(\d*d\d+\s*[+-]?\s*\d*)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    formula = match.group(1).strip().replace(" ", "")
    try:
        return roll(formula)
    except ValueError:
        return None


@dataclass
class InitResult:
    """先攻检定结果。"""
    natural: int
    total: int
    modifier: int


def roll_initiative(dex_modifier: int = 0) -> InitResult:
    """先攻检定: d20 + 敏捷修正。"""
    natural = roll("d20").natural
    total = natural + dex_modifier
    return InitResult(natural=natural, total=total, modifier=dex_modifier)
