"""每回合死亡豁免：服务端对昏迷角色的权威结算，LLM 只按结果叙事。"""

from __future__ import annotations

import logging

from src.engine.character_utils import apply_death_save
from src.engine.dice import roll
from src.engine.game_instance import GameInstance
from src.engine.language import localized_text

logger = logging.getLogger("trpg")


def resolve_round_death_saves(instance: GameInstance, rule) -> str:
    """为每个昏迷角色掷一次死亡豁免并更新状态；规则未声明时返回空串。"""
    if rule is None or rule.death_mechanic["hp_zero"] != "downed_death_saves":
        return ""
    lines: list[str] = []
    round_key = str(instance.round_number)
    round_cache = instance.death_save_outcomes.setdefault(round_key, {})
    for uid, player in list(instance.players.items()):
        cs = instance.get_character_sheet(uid)
        cached = round_cache.get(uid)
        if isinstance(cached, dict) and "roll" in cached:
            value = int(cached.get("roll", 0) or 0)
            event = str(cached.get("event") or "")
            before_status = cached.get("before_status")
            before_saves = cached.get("before_death_saves")
            current_saves = cs.get("death_saves") if isinstance(cs.get("death_saves"), dict) else None
            if (
                "before_status" in cached
                and str(cs.get("status") or "") == str(before_status or "")
                and current_saves == before_saves
            ):
                after_status = cached.get("status")
                if after_status:
                    cs["status"] = after_status
                else:
                    cs.pop("status", None)
                after_saves = cached.get("death_saves")
                if isinstance(after_saves, dict):
                    cs["death_saves"] = dict(after_saves)
                else:
                    cs.pop("death_saves", None)
                cs["deceased"] = bool(cached.get("deceased"))
                if "hp" in cached:
                    cs["hp"] = int(cached.get("hp", 0) or 0)
            instance.set_character_sheet(uid, cs)
        elif cs.get("deceased") or str(cs.get("status") or "") != "downed":
            continue
        else:
            before_saves = cs.get("death_saves") if isinstance(cs.get("death_saves"), dict) else None
            before_status = cs.get("status")
            value = roll("d20").natural
            event = apply_death_save(cs, value, instance.round_number)
            round_cache[uid] = {
                "roll": value,
                "event": event,
                "before_status": before_status,
                "before_death_saves": dict(before_saves) if isinstance(before_saves, dict) else None,
                "status": cs.get("status"),
                "death_saves": dict(cs.get("death_saves")) if isinstance(cs.get("death_saves"), dict) else None,
                "deceased": bool(cs.get("deceased")),
                "hp": int(cs.get("hp", 0) or 0),
            }
            instance.set_character_sheet(uid, cs)
        name = str(player.get("character_name") or uid)
        label = localized_text(instance.language, {
            "zh-CN": "死亡豁免", "en": "death save", "ja": "死亡セーヴ",
        })
        if event == "wake":
            detail = localized_text(instance.language, {
                "zh-CN": "自然20！恢复1HP并苏醒",
                "en": "natural 20! Regains 1 HP and wakes up",
                "ja": "自然20！1HP回復して目覚める",
            })
        elif event == "dead":
            detail = localized_text(instance.language, {
                "zh-CN": "失败满3次，死亡",
                "en": "3 failures, dies",
                "ja": "失敗3回で死亡",
            })
        elif event == "stable":
            detail = localized_text(instance.language, {
                "zh-CN": "成功满3次，伤势稳定",
                "en": "3 successes, becomes stable",
                "ja": "成功3回で安定",
            })
        else:
            saves = cs.get("death_saves") if isinstance(cs.get("death_saves"), dict) else {}
            detail = localized_text(instance.language, {
                "zh-CN": f"成功{int(saves.get('success', 0) or 0)}/失败{int(saves.get('failure', 0) or 0)}",
                "en": f"successes {int(saves.get('success', 0) or 0)}/failures {int(saves.get('failure', 0) or 0)}",
                "ja": f"成功{int(saves.get('success', 0) or 0)}/失敗{int(saves.get('failure', 0) or 0)}",
            })
        lines.append(f"【{name}】{label} d20={value} → {detail}")
        logger.info("死亡豁免: %s d20=%d event=%s (round=%d)", name, value, event, instance.round_number)
    return "\n".join(lines)
