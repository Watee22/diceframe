"""世界模板 recommended_rules：可选字段透传、清洗与兼容。"""

from __future__ import annotations

from src.webui.services.worlds import _world_template_summary


def test_recommended_rules_passthrough_and_sanitization() -> None:
    summary = _world_template_summary(
        {"world_id": "w", "recommended_rules": ["freeform_fantasy", "", "dnd5e", "freeform_fantasy", 3]},
        "w",
    )
    assert summary["recommended_rules"] == ["freeform_fantasy", "dnd5e"]


def test_recommended_rules_missing_is_empty_list() -> None:
    summary = _world_template_summary({"world_id": "w"}, "w")
    assert summary["recommended_rules"] == []
    assert summary["default_rule"] == "freeform_fantasy"
