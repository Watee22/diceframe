"""引擎全局常量 —— 单一数据源，避免多处重复定义。"""

COMBAT_INTENT_KEYWORDS: tuple[str, ...] = (
    "攻击", "战斗", "砍", "刺", "射", "踢", "踹", "砸", "揍",
    "打死", "干掉", "击杀", "劈", "挥", "突袭",
    "施法", "法术", "魔法", "格挡", "防御", "回避", "闪避",
)

# 只有明确的攻击动作才允许进入服务器伤害结算。诸如“研究魔法”、
# “保持防御距离”虽然会命中上面的广义战斗词，但绝不能被解释成攻击队友。
COMBAT_ATTACK_KEYWORDS: tuple[str, ...] = (
    "攻击", "砍", "刺", "射击", "射向", "踢", "踹", "砸", "揍",
    "打死", "干掉", "击杀", "劈", "挥砍", "突袭", "冲撞", "咬",
)

PUZZLE_KEYWORDS: tuple[str, ...] = (
    "解谜", "谜题", "检查", "调查", "搜查", "破解", "解除",
    "撬锁", "拆解", "辨认", "识别", "鉴定", "感知", "侦查",
    "追踪", "观察", "搜索", "找寻", "探索",
)

DEFAULT_HP_FORMULA = "5 + con * 3"

WEAPON_DAMAGE: dict[str, int] = {
    "徒手": 2, "拳": 2,
    "匕首": 4, "短剑": 5, "短刀": 5,
    "铁剑": 6, "长剑": 7, "弯刀": 7, "细剑": 5,
    "巨剑": 10, "大剑": 9, "战斧": 9, "巨斧": 11,
    "钉头锤": 7, "战锤": 8, "棍棒": 4, "短棍": 3,
    "长矛": 7, "长枪": 8, "戟": 9,
    "长弓": 6, "短弓": 5, "弩": 7,
    "法杖": 3, "魔杖": 3, "法器": 3,
    "皮甲": 2, "链甲": 4, "板甲": 6, "盾牌": 2,
    "左轮手枪": 8, "手枪": 7, "霰弹枪": 12, "猎枪": 10,
    "冲锋枪": 9, "步枪": 10, "手电筒": 1, "军刀": 5,
    # D&D 模板的英文/日文显示名；规则身份仍由装备数据字段承载。
    "dagger": 4, "短剣": 4, "shortsword": 5, "ショートソード": 5,
    "longsword": 7, "ロングソード": 7, "scimitar": 7, "シミター": 7,
    "rapier": 5, "レイピア": 5, "greatsword": 10, "greataxe": 11,
    "大斧": 11, "mace": 7, "メイス": 7, "warhammer": 8, "ウォーハンマー": 8,
    "quarterstaff": 3, "クォータースタッフ": 3, "staff": 3, "杖": 3,
    "spear": 7, "槍": 7, "longbow": 6, "ロングボウ": 6,
    "shortbow": 5, "ショートボウ": 5, "crossbow": 7, "クロスボウ": 7,
}

# 武器伤害骰（多语言名称，casefold 后查表）。
# 只有规则声明 critical_damage=double_damage_dice 时才消费该字段；
# 旧固定 damage 继续作为所有规则的默认与回退。
WEAPON_DAMAGE_DICE: dict[str, str] = {
    "匕首": "1d4", "dagger": "1d4", "短剣": "1d4",
    "短剑": "1d6", "shortsword": "1d6", "ショートソード": "1d6",
    "长剑": "1d8", "longsword": "1d8", "ロングソード": "1d8",
    "铁剑": "1d8", "剣": "1d8",
    "弯刀": "1d6", "scimitar": "1d6", "シミター": "1d6",
    "细剑": "1d8", "rapier": "1d8", "レイピア": "1d8",
    "巨剑": "2d6", "大剑": "2d6", "greatsword": "2d6",
    "战斧": "1d8", "巨斧": "1d12", "greataxe": "1d12", "大斧": "1d12",
    "钉头锤": "1d6", "mace": "1d6", "メイス": "1d6",
    "战锤": "1d8", "warhammer": "1d8", "ウォーハンマー": "1d8",
    "短棍": "1d6", "quarterstaff": "1d6", "クォータースタッフ": "1d6",
    "法杖": "1d6", "staff": "1d6", "杖": "1d6",
    "长矛": "1d6", "spear": "1d6", "槍": "1d6",
    "长枪": "1d10", "戟": "1d10",
    "长弓": "1d8", "longbow": "1d8", "ロングボウ": "1d8",
    "短弓": "1d6", "shortbow": "1d6", "ショートボウ": "1d6",
    "弩": "1d8", "crossbow": "1d8", "クロスボウ": "1d8",
    "飞镖": "1d4", "dart": "1d4",
}

# D&D 式 Lite 护甲类别（多语言名称，casefold 后查表）。
# light: 基础 AC + 完整 DEX；medium: 基础 AC + 封顶 DEX；
# heavy: 固定 AC 不吃 DEX；shield: 额外加值。
# 未列出的护甲回退旧版累加逻辑，不影响其他规则。
ARMOR_LITE: dict[str, dict] = {
    "leather_armor": {"category": "light", "ac_base": 11, "dex_cap": None},
    "皮甲": {"category": "light", "ac_base": 11, "dex_cap": None},
    "leather armor": {"category": "light", "ac_base": 11, "dex_cap": None},
    "革鎧": {"category": "light", "ac_base": 11, "dex_cap": None},
    "chain_mail": {"category": "heavy", "ac_base": 16, "dex_cap": 0},
    "链甲": {"category": "heavy", "ac_base": 16, "dex_cap": 0},
    "chain mail": {"category": "heavy", "ac_base": 16, "dex_cap": 0},
    "チェインメイル": {"category": "heavy", "ac_base": 16, "dex_cap": 0},
    "鳞甲": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "scale mail": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "スケイルメイル": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "胸甲": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "breastplate": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "ブレストプレート": {"category": "medium", "ac_base": 14, "dex_cap": 2},
    "板甲": {"category": "heavy", "ac_base": 18, "dex_cap": 0},
    "plate armor": {"category": "heavy", "ac_base": 18, "dex_cap": 0},
    "プレートアーマー": {"category": "heavy", "ac_base": 18, "dex_cap": 0},
    "盾牌": {"category": "shield", "ac_bonus": 2},
    "盾": {"category": "shield", "ac_bonus": 2},
    "wooden_shield": {"category": "shield", "ac_bonus": 2},
    "木盾": {"category": "shield", "ac_bonus": 2},
    "shield": {"category": "shield", "ac_bonus": 2},
    "wooden shield": {"category": "shield", "ac_bonus": 2},
    "木の盾": {"category": "shield", "ac_bonus": 2},
}

# Rules consume canonical item keys; localized names remain display data and
# are normalized at creation/fallback boundaries for compatibility with saves.
ITEM_KEY_ALIASES: dict[str, str] = {
    "匕首": "dagger", "dagger": "dagger", "短剣": "dagger",
    "短剑": "shortsword", "shortsword": "shortsword", "ショートソード": "shortsword",
    "长剑": "longsword", "longsword": "longsword", "ロングソード": "longsword",
    "弯刀": "scimitar", "scimitar": "scimitar", "シミター": "scimitar",
    "细剑": "rapier", "rapier": "rapier", "レイピア": "rapier",
    "巨剑": "greatsword", "greatsword": "greatsword",
    "巨斧": "greataxe", "大斧": "greataxe", "greataxe": "greataxe",
    "钉头锤": "mace", "mace": "mace", "メイス": "mace",
    "战锤": "warhammer", "warhammer": "warhammer", "ウォーハンマー": "warhammer",
    "短棍": "quarterstaff", "quarterstaff": "quarterstaff", "クォータースタッフ": "quarterstaff",
    "法杖": "staff", "staff": "staff", "杖": "staff",
    "长弓": "longbow", "longbow": "longbow", "ロングボウ": "longbow",
    "短弓": "shortbow", "shortbow": "shortbow", "ショートボウ": "shortbow",
    "皮甲": "leather_armor", "leather armor": "leather_armor", "革鎧": "leather_armor",
    "链甲": "chain_mail", "chain mail": "chain_mail", "チェインメイル": "chain_mail",
    "盾牌": "shield", "盾": "shield", "shield": "shield",
    "木盾": "wooden_shield", "wooden shield": "wooden_shield", "木の盾": "wooden_shield",
}


def canonical_item_key(name: object) -> str:
    """Return a stable key for known starter/combat items, else an empty key."""
    return ITEM_KEY_ALIASES.get(str(name or "").strip().casefold(), "")
