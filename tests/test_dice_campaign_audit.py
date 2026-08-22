from __future__ import annotations

import json

from scripts.audit_dice_campaigns import run_audit


def test_long_campaign_dice_audit_smoke() -> None:
    report = run_audit(
        rounds_per_rule=50,
        distribution_samples=5_000,
        seed=20260822,
    )

    assert report["ok"] is True
    assert report["total_checks"] == 400
    assert report["scenario_error_count"] == 0
    assert report["formula_error_count"] == 0
    assert report["distribution_error_count"] == 0
    assert {item["name"] for item in report["scenarios"]} == {
        "dnd5e",
        "freeform_fantasy",
        "freeform_cyberpunk",
        "freeform_wuxia",
        "freeform_coc",
        "tavern_free",
        "audit_strict_d20",
        "audit_cinematic_d20",
        "audit_custom_d100",
    }


def test_dnd_six_player_campaign_records_every_check() -> None:
    report = run_audit(
        rounds_per_rule=25,
        players_per_round=6,
        rule_ids={"dnd5e"},
        capture_details=True,
        distribution_samples=5_000,
        seed=20260822,
    )

    assert report["ok"] is True
    assert report["total_actions"] == 150
    assert report["total_checks"] == 150
    assert len(report["scenarios"]) == 1
    details = report["scenarios"][0]["details"]
    assert len(details) == 150
    assert {item["player"] for item in details} == {f"p{index}" for index in range(1, 7)}
    assert {item["round"] for item in details} == set(range(1, 26))
    assert all(item["action"].endswith("。") for item in details)
    assert all(item["independently_verified"] for item in details)
    assert {item["attribute"] for item in details} == {"str", "dex", "con", "int", "wis", "cha"}
    assert all(10 <= item["dc"] <= 18 for item in details)
    assert all(item["requested_dc"] == item["dc"] for item in details)
    assert not {item["verdict"] for item in details} & {"大成功", "大失败"}


def test_external_content_pack_rule_can_join_campaign_audit(tmp_path) -> None:
    plugin_dir = tmp_path / "sample-pack"
    rules_dir = plugin_dir / "content" / "rules"
    rules_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")
    (rules_dir / "sample_rule.json").write_text(json.dumps({
        "rule_id": "sample_pack_rule",
        "rule_name": "Sample pack rule",
        "dice_system": "d20",
        "combat_model": "hp_based",
        "max_check_dc": 20,
        "check_mechanic": {
            "dice": "d20",
            "comparison": "roll_plus_modifier_gte_target",
            "critical": {"success": 20, "failure": 1},
            "advantage": {
                "type": "d20_keep_high_low",
                "allow_explicit": True,
                "assistance_grants": "advantage",
            },
        },
        "attributes": [{"key": "focus", "name": "Focus", "min": 3, "max": 18}],
    }), encoding="utf-8")

    report = run_audit(
        rounds_per_rule=5,
        players_per_round=2,
        rule_ids={"sample_pack_rule"},
        rule_paths=[plugin_dir],
        distribution_samples=1_000,
        seed=20260822,
    )

    assert report["ok"] is True
    assert report["total_actions"] == 10
    assert report["total_checks"] == 10
    assert report["scenarios"][0]["name"] == "sample_pack_rule"
