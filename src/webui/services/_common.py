"""WebUI services 共享的常量与工具。"""

from typing import Any

_GAME_KEY_SEP = "|"
_INVALID_GAME_KEY = ("__invalid_game_key__", "", "")

# 跨 HTTP、SSE 与 service 共用的输入边界。业务限制放在 service 层，
# routes 仅重新导入，避免不同入口各自维护一份数值。
MAX_LOREBOOK_CHARS = 5000
MAX_ACTION_CHARS = 1000
MAX_ACTIONS_PER_TURN = 3
MAX_SEED_CHARS = 2000


def _is_safe_game_key_part(s: str) -> bool:
    """校验 game_key 片段不可影响存档路径结构。"""
    return "/" not in s and "\\" not in s and ".." not in s and "#" not in s and ":" not in s


def _parse_game_key(game_key: str) -> tuple[str, str, str]:
    """解析公开 game_key，并拒绝路径穿越片段。"""
    raw = str(game_key or "")
    parts = raw.split(_GAME_KEY_SEP)
    parsed = tuple(parts[:3]) if len(parts) >= 3 else (raw, "", "")
    if not all(_is_safe_game_key_part(part) for part in parsed):
        return _INVALID_GAME_KEY
    return parsed


def _is_safe_world_id(s: str) -> bool:
    """校验 world_id 不含路径遍历字符（允许中文等正常字符）。"""
    return bool(s) and "/" not in s and "\\" not in s and ".." not in s


def is_game_gm(inst: Any, user_id: str, owner_authenticated: bool = False) -> bool:
    """GM 判定统一入口：该局主 GM，或已登录 owner（多人共用管理员账号都算 GM）。

    所有 GM 门控必须走这里，避免散落的 ``== gm_uid`` 各自为政；
    后续多 GM（co_gm_uids）也只需扩展这一个函数。
    """
    if inst is None or not user_id:
        return False
    if user_id == getattr(inst, "gm_uid", ""):
        return True
    return bool(owner_authenticated)
