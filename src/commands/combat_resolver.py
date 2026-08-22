"""战斗结算解析器。

从 game_handler 拆出的多人战斗结算与先攻初始化逻辑。
"""

from __future__ import annotations

import logging

from src.engine.combat import AttackResult, resolve_attack
from src.engine.constants import COMBAT_ATTACK_KEYWORDS, WEAPON_DAMAGE
from src.engine.dice import roll_initiative
from src.engine.game_instance import GameInstance
from src.engine.language import localized_text

logger = logging.getLogger("trpg")


class CombatResolver:
    """处理战斗目标识别、攻击结算和先攻顺序。"""

    def resolve_combat(self, instance: GameInstance, actions_text: str, combat_model: str) -> str:
        """只结算每条行动中明确声明的攻击，不从汇总文本猜攻击者。

        旧实现把汇总文本里的角色标签也当作战斗内容：只要任意一句提到
        “魔法/防御”，六名角色就会被当成攻击者，并把标签中第一个玩家当
        目标。这里改为逐行动识别，目标也只能来自该行动本身。
        """
        results = []
        for action in list(instance.action_queue):
            uid = str(action.get("user_id") or "")
            if uid not in instance.players:
                continue
            action_text = str(action.get("text") or "")
            if not any(keyword in action_text for keyword in COMBAT_ATTACK_KEYWORDS):
                continue
            pdata = instance.players[uid]
            cs = instance.get_character_sheet(uid)
            char_name = str(pdata.get("character_name") or uid)

            # 寻找该行动明确点名的目标（敌人 > NPC > 其他玩家）。
            target = None
            target_name = ""
            target_uid = ""
            for enemy in instance.combat_enemies:
                enemy_name = str(enemy.get("character_name") or enemy.get("name") or "")
                if enemy_name and enemy_name in action_text:
                    target = enemy
                    target_name = enemy_name
                    break
            if target is None:
                for npc_name, npc in instance.npcs.items():
                    display_name = str(npc.get("character_name") or npc.get("name") or npc_name)
                    if display_name and display_name in action_text:
                        target = npc
                        target_name = display_name
                        break
            if target is None:
                for candidate_uid, candidate_data, candidate_sheet in instance.iter_player_sheets():
                    candidate_name = str(candidate_data.get("character_name") or "")
                    if candidate_uid != uid and candidate_name and candidate_name in action_text:
                        target = candidate_sheet
                        target["character_name"] = candidate_name
                        target_name = candidate_name
                        target_uid = candidate_uid
                        break
            # 已在战斗中时，“攻击敌人”一类泛称可落到第一个存活敌人；
            # 非战斗场景不猜目标，避免误伤玩家或 NPC。
            if target is None and instance.combat_state != "none":
                target = next(
                    (enemy for enemy in instance.combat_enemies if int(enemy.get("hp", 1) or 0) > 0),
                    None,
                )
                if target is not None:
                    target_name = str(target.get("character_name") or target.get("name") or "敌人")
            if target is None:
                continue

            # 武器
            weapon = None
            weapon_name = "徒手"
            for eq in cs.get("equipment", []):
                if eq.get("slot") == "main_hand":
                    weapon = {"name": eq.get("name", "徒手"), "damage": eq.get("damage", 2)}
                    weapon_name = eq.get("name", "徒手")
                    break
            if weapon is None:
                for wname in sorted(WEAPON_DAMAGE, key=lambda x: -len(x)):
                    if wname in actions_text:
                        weapon_name = wname
                        weapon = {"name": wname, "damage": WEAPON_DAMAGE[wname]}
                        break

            attr_value = cs.get("attributes", {}).get("str", 10)

            # PvP: 检查友军伤害
            attacker_faction = cs.get("faction", "party")
            target_faction = ""
            if target_uid:
                target_faction = instance.get_character_sheet(target_uid).get("faction", "party")
            same_faction = attacker_faction and attacker_faction == target_faction

            result = resolve_attack(
                attacker_name=char_name,
                target=target,
                weapon=weapon,
                attr_value=attr_value,
                combat_model=combat_model,
                difficulty=instance.difficulty,
            )
            # 友军伤害减半
            if same_faction and result.damage > 0:
                result = AttackResult(
                    attacker=result.attacker,
                    target=result.target,
                    damage=result.damage // 2,
                    actual_damage=result.actual_damage // 2,
                    target_hp_before=result.target_hp_before,
                    target_hp_after=target.get("hp", result.target_hp_after),
                    description=result.description + " (友军伤害减半)",
                    dice=result.dice,
                )

            results.append((char_name, weapon_name, result))
            instance.record_combat_result({
                "attacker": char_name,
                "target": target_name,
                "weapon": weapon_name,
                "damage": result.actual_damage,
                "target_hp_before": result.target_hp_before,
                "target_hp_after": result.target_hp_after,
                "description": result.description,
                "round": instance.round_number,
            })

        if not results:
            return ""

        lines = [localized_text(instance.language, {
            "zh-CN": "【系统战斗结算·必须遵循】",
            "en": "[System Combat Resolution - Must Follow]",
            "ja": "【システム戦闘結算・必ず従うこと】",
        })]
        for attacker_name, weapon_name, result in results:
            lines.append(localized_text(instance.language, {
                "zh-CN": f"{attacker_name}持{weapon_name}攻击{target_name}",
                "en": f"{attacker_name} attacks {target_name} with {weapon_name}",
                "ja": f"{attacker_name}は{weapon_name}で{target_name}を攻撃した",
            }))
            if combat_model == "hp_based" and result.dice:
                lines.append(localized_text(instance.language, {
                    "zh-CN": f"  d20={result.dice.natural} → {'命中' if result.damage > 0 else '未命中'}, 伤害={result.damage}",
                    "en": f"  d20={result.dice.natural} → {'hit' if result.damage > 0 else 'miss'}, damage={result.damage}",
                    "ja": f"  d20={result.dice.natural} → {'命中' if result.damage > 0 else '外れ'}, ダメージ={result.damage}",
                }))
            else:
                lines.append(localized_text(instance.language, {
                    "zh-CN": f"  伤害={result.damage}",
                    "en": f"  damage={result.damage}",
                    "ja": f"  ダメージ={result.damage}",
                }))
            if result.dice and result.dice.is_critical:
                lines.append(localized_text(instance.language, {
                    "zh-CN": "  ⚡ 大成功！",
                    "en": "  ⚡ Critical!",
                    "ja": "  ⚡ 大成功！",
                }))
            if result.target_hp_after <= 0:
                lines.append(localized_text(instance.language, {
                    "zh-CN": f"  💀 {target_name} 倒地！",
                    "en": f"  💀 {target_name} is down!",
                    "ja": f"  💀 {target_name} は倒れた！",
                }))

        logger.info("多人战斗结算: %d attackers → %s", len(results), target_name)
        return "\n".join(lines)

    def initiate_combat(self, instance: GameInstance) -> str:
        """初始化战斗先攻顺序。返回战斗开始公告文本。"""
        combatants: list[tuple[str, int]] = []

        for uid in instance.alive_players:
            cs = instance.get_character_sheet(uid)
            dex = cs.get("attributes", {}).get("dex", 10)
            init = roll_initiative((dex - 10) // 2)
            combatants.append((uid, init.total))
            logger.info(
                "先攻: %s dex=%d roll=%d",
                instance.players[uid].get("character_name", uid),
                dex,
                init.total,
            )

        for enemy in instance.combat_enemies:
            eid = enemy.get("name", enemy.get("character_name", "敌人"))
            dex = enemy.get("character_sheet", {}).get("attributes", {}).get("dex", 10)
            init = roll_initiative((dex - 10) // 2)
            combatants.append((eid, init.total))

        combatants.sort(key=lambda x: -x[1])
        instance.begin_combat([combatant[0] for combatant in combatants])

        order_text = " → ".join(
            f"{instance.players[uid].get('character_name', uid)}({score})"
            if uid in instance.players else f"{uid}({score})"
            for uid, score in combatants
        )
        logger.info("战斗开始: order=%s", order_text)
        return f"⚔ 战斗开始！先攻顺序: {order_text}"
