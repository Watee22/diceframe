from src.commands.state_update_applier import discard_unresolved_player_damage
from src.engine.game_instance import GameInstance


def _instance(verdict: str | None = None) -> GameInstance:
    instance = GameInstance(("web", "guard", "bot"))
    instance.round_number = 7
    instance.players = {
        "p1": {
            "character_name": "冒险者",
            "character_sheet": {"hp": 10, "max_hp": 10, "deceased": False},
        }
    }
    instance.last_checks = [] if verdict is None else [{"actor_uid": "p1", "verdict": verdict}]
    return instance


def test_damage_without_check_is_discarded() -> None:
    update = {"players": {"p1": {"hp_change": -10}}}
    discard_unresolved_player_damage(_instance(), update)
    assert update == {"players": {}}


def test_damage_after_successful_check_is_discarded_but_other_updates_remain() -> None:
    update = {"players": {"p1": {"hp_change": -10, "status": "警戒"}}}
    discard_unresolved_player_damage(_instance("成功"), update)
    assert update == {"players": {"p1": {"status": "警戒"}}}


def test_damage_after_failed_check_is_kept() -> None:
    update = {"players": {"p1": {"hp_change": -4}}}
    discard_unresolved_player_damage(_instance("失败"), update)
    assert update == {"players": {"p1": {"hp_change": -4}}}
