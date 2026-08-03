from src.lorebook.store import LorebookStore
from src.webui.services.character_cards import _import_tavern_as_npc


class _Api:
    """最小 api：只暴露 _lore 和 _rebuild_lorebook_index 给 NPC 导入用。"""
    def __init__(self, store):
        self._lore = store

    def _rebuild_lorebook_index(self, world_id):
        pass


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
