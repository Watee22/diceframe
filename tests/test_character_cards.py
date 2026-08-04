from src.lorebook.store import LorebookStore
from src.webui.services.character_cards import _import_tavern_as_npc


class _Api:
    """最小 api：只暴露 _lore 和 _rebuild_lorebook_index 给 NPC 导入用。"""
    def __init__(self, store):
        self._lore = store

    def _rebuild_lorebook_index(self, world_id):
        pass


def test_export_preserves_business_fields_strips_runtime_markers(tmp_path):
    """导出去掉运行期插件标记，保留 source/raw_sillytavern 业务字段。"""
    import json
    from src.webui.services.character_cards import export_character_cards

    class _Api:
        def __init__(self, path):
            self._character_cards_path = path

    cards_path = tmp_path / "cards.json"
    api = _Api(cards_path)
    card = {
        "id": "st_123", "schema_version": 2, "character_name": "Himmel",
        "attributes": {}, "skills": [],
        "source": "SillyTavern: himmel.png",
        "raw_sillytavern": {"name": "Himmel", "description": "冒险者"},
        "source_plugin": "napcat", "plugin_content_id": "p1",
    }
    cards_path.write_text(json.dumps([card], ensure_ascii=False), encoding="utf-8")
    result = export_character_cards(api, ["st_123"])
    assert result["ok"] is True
    payload = json.loads(result["payload"].decode("utf-8"))
    # 业务字段保留
    assert payload["raw_sillytavern"] == {"name": "Himmel", "description": "冒险者"}
    assert payload["source"] == "SillyTavern: himmel.png"
    # 运行期插件标记去掉
    assert "source_plugin" not in payload
    assert "plugin_content_id" not in payload


def test_export_batch_disambiguates_same_name(tmp_path):
    """批量导出同名卡时 zip 内文件名不冲突，不互相覆盖。"""
    import io
    import json
    import zipfile
    from src.webui.services.character_cards import export_character_cards

    class _Api:
        def __init__(self, path):
            self._character_cards_path = path

    cards_path = tmp_path / "cards.json"
    api = _Api(cards_path)
    cards = [
        {"id": "c1", "schema_version": 2, "character_name": "艾琳", "attributes": {}},
        {"id": "c2", "schema_version": 2, "character_name": "艾琳", "attributes": {}},
    ]
    cards_path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    result = export_character_cards(api, ["c1", "c2"])
    assert result["ok"] is True
    assert result["content_type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result["payload"])) as zf:
        names = zf.namelist()
        assert len(names) == 2  # 两张都保留
        assert len(set(names)) == 2  # 文件名不重复


def test_export_import_roundtrip_preserves_raw_sillytavern(tmp_path):
    """导出→导入无损往返：raw_sillytavern 保留，识别为 DiceFrame 卡原样入库。"""
    import asyncio
    import base64
    import json
    from src.webui.services.character_cards import export_character_cards, import_character_card

    class _Api:
        def __init__(self, path):
            self._character_cards_path = path

    cards_path = tmp_path / "cards.json"
    api = _Api(cards_path)
    card = {
        "id": "st_123", "schema_version": 2, "character_name": "Himmel",
        "attributes": {}, "skills": [], "source": "SillyTavern: himmel.png",
        "raw_sillytavern": {"name": "Himmel", "description": "冒险者"},
    }
    cards_path.write_text(json.dumps([card], ensure_ascii=False), encoding="utf-8")
    exported = export_character_cards(api, ["st_123"])
    file_data = base64.b64encode(exported["payload"]).decode()
    imported = asyncio.run(import_character_card(api, file_data=file_data, file_name="Himmel.json"))
    assert imported["ok"] is True
    assert imported["format"] == "diceframe"
    assert imported["card"]["raw_sillytavern"] == card["raw_sillytavern"]


def test_import_tavern_as_npc_creates_npc_and_book_entries(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        store.create_world("w1", "测试世界", description="", language="zh-CN")
        tavern = {
            "name": "Himmel",
            "description": "一位老练的冒险者",
            "personality": "温和而坚定",
            "scenario": "酒馆偶遇",
            "first_mes": "你好，旅行者",
            "tags": ["英雄", "冒险者"],
            "character_book": [
                {"keys": ["剑", "武器"], "content": "Himmel 的佩剑", "comment": "佩剑"},
                {"keys": ["过去"], "content": "Himmel 的往事", "comment": "往事"},
            ],
        }
        result = _import_tavern_as_npc(_Api(store), tavern, "w1")

        assert result["ok"] is True
        assert result["imported_as"] == "npc"
        assert result["npc_name"] == "Himmel"
        assert result["lorebook_entries"] == 2

        npc = store.get_entry("w1_tavern_Himmel")
        assert npc is not None
        assert npc["type"] == "npc"
        assert npc["tier"] == "core"
        assert "Himmel" in npc["keywords"]
        assert "英雄" in npc["keywords"]
        assert "描述: 一位老练的冒险者" in npc["content"]
        assert "性格: 温和而坚定" in npc["content"]

        book1 = store.get_entry("w1_tavern_Himmel_book_0")
        assert book1 is not None
        assert book1["type"] == "other"
        assert "剑" in book1["keywords"]
        assert book1["content"] == "Himmel 的佩剑"

        # 幂等：再导一次是更新而非新增，条目数不变（1 npc + 2 book = 3）
        tavern["description"] = "更新后的描述"
        _import_tavern_as_npc(_Api(store), tavern, "w1")
        npc2 = store.get_entry("w1_tavern_Himmel")
        assert "更新后的描述" in npc2["content"]
        assert len(store.list_entries("w1")) == 3
    finally:
        store.close()


def test_import_tavern_as_npc_requires_world(tmp_path):
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        api = _Api(store)
        # 无 world_id
        assert _import_tavern_as_npc(api, {"name": "X"}, "")["ok"] is False
        # 世界不存在
        assert _import_tavern_as_npc(api, {"name": "X"}, "no-such-world")["ok"] is False
    finally:
        store.close()


def test_import_tavern_carries_play_directives_and_nsfw_warning(tmp_path):
    """system_prompt / post_history_instructions 进 NPC content；NSFW 卡返回标记。"""
    from src.webui.services.character_cards import _tavern_has_nsfw
    store = LorebookStore(tmp_path / "lore.db")
    store.open()
    try:
        store.create_world("w1", "测试世界", description="", language="zh-CN")
        tavern = {
            "name": "Sucrose",
            "description": "一位生物炼金术士",
            "personality": "社恐、好奇、笨拙",
            "scenario": "森林偶遇",
            "first_mes": "啊、啊啦…",
            "system_prompt": "短句；只写角色行为，不写玩家的动作。",
            "post_history_instructions": "耳朵被提及时会慌乱地躲起来。",
            "tags": ["Game Characters", "Female", "Cute"],
            "character_book": None,
        }
        result = _import_tavern_as_npc(_Api(store), tavern, "w1")
        assert result["ok"] is True
        assert "nsfw_warning" not in result  # 无 NSFW 标记，不给警告

        npc = store.get_entry("w1_tavern_Sucrose")
        assert npc is not None
        assert "扮演指令: 短句；只写角色行为，不写玩家的动作。" in npc["content"]
        assert "后续指令: 耳朵被提及时会慌乱地躲起来。" in npc["content"]

        # NSFW 标记 -> 返回 True（中英文标记都覆盖）
        assert _tavern_has_nsfw({**tavern, "tags": ["NSFW", "Submissive"]}) is True
        assert _tavern_has_nsfw(tavern) is False
    finally:
        store.close()
