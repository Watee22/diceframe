from __future__ import annotations

import json

from scripts.audit_rules import audit_world_file, iter_rule_files, iter_world_files


def test_external_content_pack_discovers_rules_and_worlds(tmp_path) -> None:
    plugin_dir = tmp_path / "sample-pack"
    rules_dir = plugin_dir / "content" / "rules"
    worlds_dir = plugin_dir / "content" / "worlds"
    rules_dir.mkdir(parents=True)
    worlds_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")
    rule_path = rules_dir / "sample.json"
    world_path = worlds_dir / "sample.json"
    rule_path.write_text(json.dumps({"rule_id": "sample"}), encoding="utf-8")
    world_path.write_text(json.dumps({
        "world_id": "sample_world",
        "default_rule": "sample",
    }), encoding="utf-8")

    assert rule_path.resolve() in iter_rule_files([plugin_dir])
    assert world_path.resolve() in iter_world_files([plugin_dir])
    assert audit_world_file(world_path, {"sample"}) == []


def test_world_audit_rejects_missing_rule_reference(tmp_path) -> None:
    world_path = tmp_path / "broken_world.json"
    world_path.write_text(json.dumps({
        "world_id": "broken_world",
        "default_rule": "missing_rule",
    }), encoding="utf-8")

    errors = audit_world_file(world_path, {"available_rule"})

    assert len(errors) == 1
    assert "missing_rule" in errors[0]
