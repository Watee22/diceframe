"""LorebookStore 集成测试 —— CRUD + 迁移 + 级联删除。"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from src.lorebook.bootstrap import ensure_world_from_template
from src.lorebook.store import LorebookStore


def _temp_store():
    """创建临时存储用于测试。"""
    t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    t.close()
    store = LorebookStore(Path(t.name))
    store.open()
    return store, Path(t.name)


class TestCreateAndGetWorld:
    def test_create_world(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试世界", description="测试描述", author="tester")
            w = store.get_world("w1")
            assert w is not None
            assert w["name"] == "测试世界"
            assert w["description"] == "测试描述"
            assert w["author"] == "tester"
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_list_worlds(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "世界1")
            store.create_world("w2", "世界2")
            worlds = store.list_worlds()
            assert len(worlds) == 2
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_builtin_template_repairs_legacy_world_language_without_losing_entries(self):
        store, path = _temp_store()
        try:
            store.create_world("world_en", "Legacy World", language="zh-CN")
            store.add_entry({
                "id": "entry_1",
                "world_id": "world_en",
                "name": "Existing entry",
                "keywords": [],
                "content": "Keep me",
            })

            inserted = ensure_world_from_template(store, "world_en", {
                "world_name": "English World",
                "language": "en",
                "starter_lorebook": [],
            })

            assert inserted == 0
            assert store.get_world("world_en")["language"] == "en"
            assert store.get_entry("entry_1")["content"] == "Keep me"
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_delete_world_cascade(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "条目1",
                            "keywords": ["测试"], "content": "内容"})
            store.delete_world_cascade("w1")
            assert store.get_world("w1") is None
            assert store.get_entry("e1") is None
        finally:
            store.close()
            path.unlink(missing_ok=True)


class TestEntryCRUD:
    def test_add_and_get_entry(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试世界")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "龙",
                            "keywords": ["龙", "火"], "content": "一条火龙",
                            "type": "npc", "tier": "core"})
            entry = store.get_entry("e1")
            assert entry is not None
            assert entry["name"] == "龙"
            assert "龙" in entry["keywords"]
            assert "火" in entry["keywords"]
            assert entry["tier"] == "core"
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_update_entry(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "旧名称",
                            "keywords": ["旧"], "content": "旧内容"})
            store.update_entry("e1", {"name": "新名称", "content": "新内容"})
            entry = store.get_entry("e1")
            assert entry["name"] == "新名称"
            assert entry["content"] == "新内容"
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_list_entries_by_world(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "世界1")
            store.create_world("w2", "世界2")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "条目1",
                            "keywords": [], "content": "a"})
            store.add_entry({"id": "e2", "world_id": "w2", "name": "条目2",
                            "keywords": [], "content": "b"})
            w1_entries = store.list_entries("w1")
            assert len(w1_entries) == 1
            assert w1_entries[0]["name"] == "条目1"
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_search_entries(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "哥布林",
                            "keywords": ["哥布林"], "content": "绿色的小怪物"})
            store.add_entry({"id": "e2", "world_id": "w1", "name": "巨龙",
                            "keywords": ["龙"], "content": "会喷火"})
            results = store.search_entries("w1", "龙")
            assert len(results) == 1
            assert results[0]["name"] == "巨龙"
        finally:
            store.close()
            path.unlink(missing_ok=True)


class TestMigration:
    def test_new_columns_exist(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试")
            store.add_entry({
                "id": "e1", "world_id": "w1", "name": "test",
                "keywords": ["test"], "content": "test",
                "sticky": 3, "cooldown": 2, "delay": 1,
                "order": 50, "probability": 80, "group": "g1",
                "group_weight": 10,
            })
            entry = store.get_entry("e1")
            assert entry["sticky"] == 3
            assert entry["cooldown"] == 2
            assert entry["delay"] == 1
            assert entry["order"] == 50
            assert entry["probability"] == 80
            assert entry["group"] == "g1"
            assert entry["group_weight"] == 10
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_default_values(self):
        store, path = _temp_store()
        try:
            store.create_world("w1", "测试")
            store.add_entry({"id": "e1", "world_id": "w1", "name": "test",
                            "keywords": [], "content": "test"})
            entry = store.get_entry("e1")
            assert entry["sticky"] == 0
            assert entry["cooldown"] == 0
            assert entry["delay"] == 0
            assert entry["order"] == 100
            assert entry["probability"] == 100
            assert entry["group"] == ""
            assert entry["group_weight"] == 1
        finally:
            store.close()
            path.unlink(missing_ok=True)

    def test_backfills_source_plugin_from_old_ids(self):
        """老库无 source_plugin 列：打开时迁移加列 + 从 id 的 _plugin_ 标记回填插件来源。"""
        import gc
        import sqlite3
        t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        t.close()
        path = Path(t.name)
        try:
            # 构造旧库：无 source_plugin 列，插入老格式条目
            conn = sqlite3.connect(str(path))
            conn.execute("CREATE TABLE worlds (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                         "description TEXT DEFAULT '', language TEXT DEFAULT 'zh-CN', "
                         "author TEXT DEFAULT '', version TEXT DEFAULT '1.0', "
                         "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
                         "updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
            conn.execute("INSERT INTO worlds (id, name) VALUES ('w1', '测试')")
            conn.execute("CREATE TABLE lorebook_entries ("
                         "id TEXT PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), name TEXT NOT NULL, "
                         "type TEXT DEFAULT 'other', keywords TEXT DEFAULT '[]', content TEXT DEFAULT '', "
                         "tier TEXT DEFAULT 'background')")
            conn.executemany(
                "INSERT INTO lorebook_entries (id, world_id, name, type, content) VALUES (?,?,?,?,?)",
                [
                    # 自动灌入格式：_plugin_{pid}_
                    ("frieren_journey_world_plugin_frieren-journey_e1", "w1", "P", "location", "c"),
                    # 一键导入格式：_plugin_{kind}_{pid}_
                    ("myworld_plugin_npc_frieren-journey_hero", "w1", "N", "npc", "c"),
                    # 用户自建，无标记
                    ("myworld_user_note", "w1", "U", "location", "c"),
                ],
            )
            conn.commit()
            conn.close()
            del conn
            gc.collect()

            store = LorebookStore(path)
            store.open()
            try:
                e1 = store.get_entry("frieren_journey_world_plugin_frieren-journey_e1")
                e2 = store.get_entry("myworld_plugin_npc_frieren-journey_hero")
                e3 = store.get_entry("myworld_user_note")
                assert e1["source_plugin"] == "frieren-journey"
                assert e2["source_plugin"] == "frieren-journey"
                assert e3["source_plugin"] == ""
            finally:
                store.close()
                del store
                gc.collect()
        finally:
            # Windows 上 sqlite WAL 句柄释放是异步的，清理失败不影响测试结果
            for _ in range(20):
                try:
                    path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_drop_legacy_type_check_allows_spell_class(self):
        """老库 type 列带 CHECK 约束：打开时重建表去掉约束，能插入 spell/class。"""
        import gc
        import sqlite3
        t = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        t.close()
        path = Path(t.name)
        try:
            # 构造老库：带 CHECK 约束，无 source_plugin 列
            conn = sqlite3.connect(str(path))
            conn.execute("CREATE TABLE worlds (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                         "description TEXT DEFAULT '', language TEXT DEFAULT 'zh-CN', "
                         "author TEXT DEFAULT '', version TEXT DEFAULT '1.0', "
                         "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
                         "updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
            conn.execute("INSERT INTO worlds (id, name) VALUES ('w1', '测试')")
            conn.execute("CREATE TABLE lorebook_entries ("
                         "id TEXT PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), name TEXT NOT NULL, "
                         "type TEXT NOT NULL DEFAULT 'other' CHECK(type IN ('npc','location','item','event','puzzle','faction','other')), "
                         "keywords TEXT DEFAULT '[]', content TEXT DEFAULT '', tier TEXT DEFAULT 'background')")
            conn.execute("INSERT INTO lorebook_entries (id, world_id, name, type) VALUES ('e1','w1','老条目','location')")
            conn.commit()
            conn.close()
            del conn
            gc.collect()

            store = LorebookStore(path)
            store.open()
            try:
                # 旧库已含 w1；不要 create_world（INSERT OR REPLACE 会级联删 e1）
                # 新类型 spell/class 能插入（CHECK 已去掉）
                store.add_entry({"id": "s1", "world_id": "w1", "name": "火球", "type": "spell", "content": "c"})
                store.add_entry({"id": "c1", "world_id": "w1", "name": "战士", "type": "class", "content": "c"})
                assert store.get_entry("s1")["type"] == "spell"
                assert store.get_entry("c1")["type"] == "class"
                # 老条目保留
                assert store.get_entry("e1")["type"] == "location"
            finally:
                store.close()
                del store
                gc.collect()
        finally:
            for _ in range(20):
                try:
                    path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.1)
