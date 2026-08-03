"""角色卡库服务：列表 / 保存 / 更新 / 删除 / SillyTavern 卡导入。"""

from __future__ import annotations

import base64
import copy
import io
import json
import logging
import tempfile
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.engine.character_utils import parse_tavern_card

if TYPE_CHECKING:
    from src.webui.api import WebAPI

logger = logging.getLogger("trpg")


def _read_cards(api: "WebAPI") -> list[dict[str, Any]]:
    path = api._character_cards_path
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        logger.exception("读取角色卡库失败: %s", path)
        return []


def _write_cards(api: "WebAPI", cards: list[dict[str, Any]]) -> None:
    path = api._character_cards_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _card_signature(card: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """同一张仓库卡的稳定指纹，用于避免 AI 生成后微调产生重复卡。"""
    return (
        str(card.get("character_name") or "").strip().lower(),
        str(card.get("race") or "").strip().lower(),
        str(card.get("class") or "").strip().lower(),
        str(card.get("background") or "").strip().lower(),
        str(card.get("rule_id") or "").strip().lower(),
    )


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str, str]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        sig = _card_signature(card)
        if not sig[0]:
            sig = (str(card.get("id") or f"anon_{len(order)}"), "", "", "", "")
        if sig not in seen:
            order.append(sig)
        seen[sig] = card
    return [seen[sig] for sig in order]


def _to_character_card(character: dict, source: str = "") -> dict[str, Any]:
    cs = character.get("character_sheet", {}) if isinstance(character.get("character_sheet"), dict) else character
    name = character.get("character_name") or cs.get("character_name") or "冒险者"
    card: dict[str, Any] = {
        "id": character.get("card_id") or character.get("id") or cs.get("card_id") or cs.get("id") or f"card_{int(time.time_ns())}",
        "schema_version": 2,
        "character_name": name,
        "race": cs.get("race", character.get("race", "人类")),
        "class": cs.get("class", character.get("class", "冒险者")),
        "source": source,
    }
    # A library card is a reusable blueprint, not a snapshot of one running
    # game. Runtime-only HP, XP, death and temporary status are recomputed when
    # the card joins a game under its target rule.
    for key, default in (
        ("identity", {}),
        ("attributes", {}),
        ("skills", []),
        ("background", ""),
        ("equipment", []),
        ("inventory", []),
        ("key_items", []),
        ("gold", 30),
        ("currency", {}),
        ("portrait", {}),
    ):
        value = cs.get(key, character.get(key, default))
        card[key] = copy.deepcopy(value)
    for key in ("rule_id", "rule_name", "rule_version", "mechanics", "language"):
        value = character.get(key, cs.get(key, ""))
        if value not in (None, ""):
            card[key] = str(value)
    # 插件导入的卡带来源标记（source_plugin / plugin_content_id），保存时必须透传；
    # 否则卸载清理按 source_plugin 过滤会匹配不到，插件卡成了无法清理的残留。
    for key in ("source_plugin", "plugin_content_id"):
        value = character.get(key, cs.get(key))
        if value not in (None, ""):
            card[key] = value
    return card


def list_character_cards(api: "WebAPI") -> dict[str, Any]:
    cards = _read_cards(api)
    deduped = _dedupe_cards(cards)
    if len(deduped) != len(cards):
        _write_cards(api, deduped)
        cards = deduped
    return {"cards": cards, "total": len(cards)}


def save_character_card(api: "WebAPI", character: dict) -> dict[str, Any]:
    card = _to_character_card(character, source=str(character.get("source") or "角色卡库"))
    cards = _read_cards(api)
    sig = _card_signature(card)
    for existing in cards:
        if existing.get("id") == card["id"] or _card_signature(existing) == sig:
            card["id"] = existing.get("id") or card["id"]
            break
    cards = [
        c for c in cards
        if c.get("id") != card["id"] and _card_signature(c) != sig
    ]
    cards.append(card)
    cards = _dedupe_cards(cards)
    _write_cards(api, cards)
    return {"ok": True, "card": card}


def update_character_card(api: "WebAPI", card_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    cards = _dedupe_cards(_read_cards(api))
    for idx, old in enumerate(cards):
        if old.get("id") != card_id:
            continue
        updated = {**old}
        for key in (
            "character_name", "race", "class", "background", "gold", "source",
            "rule_id", "rule_name", "rule_version", "mechanics", "language",
        ):
            if key in patch:
                updated[key] = patch[key]
        for key in ("identity", "attributes", "skills", "equipment", "inventory", "key_items", "currency", "portrait"):
            if key in patch and isinstance(patch[key], (dict, list)):
                updated[key] = patch[key]
        updated["schema_version"] = 2
        updated["id"] = card_id
        cards[idx] = updated
        _write_cards(api, cards)
        return {"ok": True, "card": updated}
    return {"ok": False, "error": f"角色卡不存在: {card_id}"}


def delete_character_card(api: "WebAPI", card_id: str) -> dict[str, Any]:
    cards = _dedupe_cards(_read_cards(api))
    kept = [c for c in cards if c.get("id") != card_id]
    if len(kept) == len(cards):
        return {"ok": False, "error": f"角色卡不存在: {card_id}"}
    _write_cards(api, kept)
    return {"ok": True, "card_id": card_id}


def _tavern_to_character_card(tavern: dict, file_name: str = "") -> dict[str, Any]:
    background_parts = []
    for label, key in (("描述", "description"), ("性格", "personality"),
                       ("场景", "scenario"), ("初次发言", "first_mes")):
        value = (tavern.get(key) or "").strip()
        if value:
            background_parts.append(f"{label}: {value}")
    # 酒馆卡的扮演指令：system_prompt / post_history_instructions 一并带进 background，
    # AI 扮演该角色时能读到行为约束（game_lifecycle 会把 background 送进 prompt）。
    for label, key in (("扮演指令", "system_prompt"), ("后续指令", "post_history_instructions")):
        value = (tavern.get(key) or "").strip()
        if value:
            background_parts.append(f"{label}: {value}")
    source = f"SillyTavern: {file_name}" if file_name else "SillyTavern"
    if tavern.get("character_book"):
        source += f"（含 {len(tavern['character_book'])} 条角色世界书）"
    return {
        "id": f"st_{int(time.time_ns())}",
        "schema_version": 2,
        "character_name": tavern.get("name") or "未命名",
        "race": "人类",
        "class": "冒险者",
        "attributes": {},
        "skills": [],
        "background": "\n".join(background_parts),
        "equipment": [],
        "gold": 30,
        "source": source,
        "rule_id": "",
        "raw_sillytavern": tavern,
    }


_NSFW_MARKERS = ("nsfw", "18+", "成人", "explicit", "lewd", "porn", "erotic", "submissive", "dominant", "bdsm", "sensual", "intimate")


def _tavern_has_nsfw(tavern: dict) -> bool:
    """检测酒馆卡是否带成人内容标记（NSFW/18+）。返回布尔，文案由前端 i18n 按语言显示。"""
    haystack_parts: list[str] = []
    tags = tavern.get("tags")
    if isinstance(tags, list):
        haystack_parts.extend(str(t).lower() for t in tags if str(t).strip())
    for key in ("system_prompt", "post_history_instructions", "description"):
        value = str(tavern.get(key) or "").strip()
        if value:
            haystack_parts.append(value.lower())
    haystack = " ".join(haystack_parts)
    return any(marker in haystack for marker in _NSFW_MARKERS)


def _import_tavern_as_npc(api: "WebAPI", tavern: dict, world_id: str) -> dict[str, Any]:
    """把酒馆卡导入为指定世界的 NPC 世界书条目，并拆入内嵌角色世界书。

    酒馆卡本质是「AI 扮演的角色」，落成 NPC 比塞进 TRPG 角色卡（强填 race/class/
    属性）更自然：description/personality/scenario/first_mes 拼成条目 content，
    名字+tags 做 keywords 触发出场；内嵌 character_book 拆成同世界 other 条目。
    """
    if not world_id:
        return {"ok": False, "error": "导入为 NPC 需要选择目标世界"}
    if not api._lore:
        return {"ok": False, "error": "世界书库未启用"}
    if not api._lore.get_world(world_id):
        return {"ok": False, "error": "目标世界不存在"}
    name = str(tavern.get("name") or "未命名").strip()
    safe_name = name.replace(" ", "_") or "npc"
    entry_id = f"{world_id}_tavern_{safe_name}"
    keywords = [name] + [str(t).strip() for t in (tavern.get("tags") or []) if str(t).strip()]
    content_parts: list[str] = []
    for label, key in (("描述", "description"), ("性格", "personality"),
                       ("背景", "scenario"), ("初次见面", "first_mes")):
        value = str(tavern.get(key) or "").strip()
        if value:
            content_parts.append(f"{label}: {value}")
    # 酒馆卡的扮演指令：system_prompt / post_history_instructions 一并进 content，
    # AI 扮演该 NPC 时能读到行为约束（世界书条目 content 会进 lorebook_matches）。
    for label, key in (("扮演指令", "system_prompt"), ("后续指令", "post_history_instructions")):
        value = str(tavern.get(key) or "").strip()
        if value:
            content_parts.append(f"{label}: {value}")
    npc_entry = {
        "id": entry_id,
        "world_id": world_id,
        "name": name,
        "type": "npc",
        "keywords": keywords[:12],
        "content": "\n".join(content_parts),
        "tier": "core",
    }
    if api._lore.get_entry(entry_id):
        api._lore.update_entry(entry_id, npc_entry)
    else:
        api._lore.add_entry(npc_entry)
    # 内嵌角色世界书 -> 同世界的 other 条目
    book = tavern.get("character_book") or []
    book_imported = 0
    if isinstance(book, list):
        for idx, item in enumerate(book):
            if not isinstance(item, dict):
                continue
            book_id = f"{world_id}_tavern_{safe_name}_book_{idx}"
            book_entry = {
                "id": book_id,
                "world_id": world_id,
                "name": str(item.get("comment") or item.get("name") or f"{name} 世界书{idx}"),
                "type": "other",
                "keywords": [str(k).strip() for k in (item.get("keys") or []) if str(k).strip()],
                "content": str(item.get("content") or ""),
                "tier": "background",
            }
            if api._lore.get_entry(book_id):
                api._lore.update_entry(book_id, book_entry)
            else:
                api._lore.add_entry(book_entry)
            book_imported += 1
    api._rebuild_lorebook_index(world_id)
    logger.info("酒馆卡已导入为 NPC: %s -> world=%s（含 %d 条世界书）", name, world_id, book_imported)
    result: dict[str, Any] = {"ok": True, "imported_as": "npc", "npc_name": name, "world_id": world_id, "lorebook_entries": book_imported}
    if _tavern_has_nsfw(tavern):
        result["nsfw_warning"] = True
    return result


def _is_diceframe_card(data: dict) -> bool:
    """判断 JSON 是否为 DiceFrame 自家角色卡格式（vs 酒馆 chara_card 格式）。

    DiceFrame 卡特征：顶层有 schema_version + 至少一个 TRPG 特有字段
    （attributes / skills / rule_id / mechanics）。酒馆卡是 {data: {...}} 包裹
    或含 description/personality 的纯酒馆结构，不带这些字段。
    """
    if not isinstance(data, dict):
        return False
    if "data" in data and isinstance(data["data"], dict):
        return False  # chara_card_v2 用 data 包裹，是酒馆格式
    if int(data.get("schema_version") or 0) != 2:
        return False
    return any(key in data for key in ("attributes", "skills", "rule_id", "mechanics", "equipment", "inventory"))


async def import_character_card(api: "WebAPI", file_data: str = "", file_name: str = "card.json",
                                target: str = "character_card", world_id: str = "") -> dict[str, Any]:
    if not file_data:
        return {"ok": False, "error": "未提供文件数据"}
    raw_bytes = base64.b64decode(file_data)
    safe_name = Path(file_name).name or "card.json"

    # DiceFrame 自家卡格式：原样存入卡库（无损），不转酒馆字段
    try:
        as_json = json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        as_json = None
    if as_json is not None and _is_diceframe_card(as_json):
        if target == "npc":
            return {"ok": False, "error": "DiceFrame 角色卡不支持导入为 NPC，请选择「导入为角色卡」"}
        card = dict(as_json)
        card.setdefault("character_name", card.get("character_name") or card.get("name") or "未命名")
        cards = _read_cards(api)
        cards.append(card)
        _write_cards(api, cards)
        return {"ok": True, "card": card, "imported_as": "character_card", "format": "diceframe"}

    tmp_path = Path(tempfile.gettempdir()) / f"trpg_card_import_{int(time.time_ns())}_{safe_name}"
    tmp_path.write_bytes(raw_bytes)
    try:
        tavern = parse_tavern_card(str(tmp_path))
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
    if "error" in tavern:
        return {"ok": False, "error": tavern["error"]}
    if target == "npc":
        return _import_tavern_as_npc(api, tavern, world_id)
    card = _tavern_to_character_card(tavern, safe_name)
    cards = _read_cards(api)
    cards.append(card)
    _write_cards(api, cards)
    result: dict[str, Any] = {"ok": True, "card": card, "imported_as": "character_card", "format": "tavern"}
    if _tavern_has_nsfw(tavern):
        result["nsfw_warning"] = True
    return result


def export_character_cards(api: "WebAPI", card_ids: list[str]) -> dict[str, Any]:
    """批量导出 DiceFrame 角色卡：单张返回 JSON 文本，多张打包 zip。

    导出的是 DiceFrame 自家格式（含 attributes/skills/rule_id 等），
    与原样导入接口无损往返；不转酒馆格式。
    """
    card_ids = [str(c).strip() for c in card_ids if str(c).strip()] if isinstance(card_ids, list) else []
    if not card_ids:
        return {"ok": False, "error": "请选择要导出的角色卡"}
    cards = _read_cards(api)
    selected = [c for c in cards if str(c.get("id") or "") in set(card_ids)]
    if not selected:
        return {"ok": False, "error": "未找到所选角色卡"}

    # 导出时去掉运行期来源标记，保留业务字段
    skip = {"source", "source_plugin", "plugin_content_id", "raw_sillytavern"}
    payloads: list[tuple[str, str]] = []
    for card in selected:
        clean = {k: v for k, v in card.items() if k not in skip}
        name = str(clean.get("character_name") or clean.get("name") or "角色卡")
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip() or "character"
        payloads.append((f"{safe}.json", json.dumps(clean, ensure_ascii=False, indent=2)))

    if len(payloads) == 1:
        filename, content = payloads[0]
        return {"ok": True, "filename": filename, "content_type": "application/json", "payload": content.encode("utf-8")}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in payloads:
            zf.writestr(name, content)
    return {"ok": True, "filename": "characters_export.zip", "content_type": "application/zip", "payload": buffer.getvalue()}

