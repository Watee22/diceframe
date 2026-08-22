"""GM 判定统一入口测试：主 GM / 已登录 owner（多人共用管理员账号）/ 空身份。"""

from src.engine.game_instance import GameInstance, GameRegistry
from src.webui.api import can_modify_character
from src.webui.routes.games import _gm_only_inst
from src.webui.services._common import _GAME_KEY_SEP, is_game_gm


class DummyAPI:
    def __init__(self, registry):
        self._reg = registry

    def _parse_key(self, game_key: str) -> tuple:
        return tuple(game_key.split(_GAME_KEY_SEP))


class FakeRequest(dict):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app


def _inst() -> GameInstance:
    inst = GameInstance(game_key=("web", "g", "bot"))
    inst.gm_uid = "gm_session"
    inst.players["p1"] = {"character_name": "玩家", "character_sheet": {"deceased": False}}
    return inst


def test_gm_uid_is_gm():
    assert is_game_gm(_inst(), "gm_session") is True


def test_other_session_is_not_gm():
    assert is_game_gm(_inst(), "other_session") is False


def test_owner_authenticated_is_gm():
    """多人共用管理员账号：任何已登录 owner 会话都算 GM。"""
    assert is_game_gm(_inst(), "other_session", owner_authenticated=True) is True


def test_empty_identity_is_never_gm():
    assert is_game_gm(_inst(), "", owner_authenticated=True) is False
    assert is_game_gm(None, "x", owner_authenticated=True) is False


def test_can_modify_character_includes_owner():
    assert can_modify_character("other", "p1", "gm_session") is False
    assert can_modify_character("other", "p1", "gm_session", owner=True) is True
    assert can_modify_character("", "p1", "gm_session", owner=True) is False


def test_gm_only_route_allows_owner_session(tmp_path):
    registry = GameRegistry(tmp_path)
    inst = _inst()
    registry.register(inst)

    class Subsystems:
        pass

    subs = Subsystems()
    subs.registry = registry
    app = {"subsystems": subs, "api": DummyAPI(registry)}
    gk = _GAME_KEY_SEP.join(("web", "g", "bot"))

    _, denied = _gm_only_inst(FakeRequest(app, **{"user_id": "other_session"}), gk)
    assert denied is not None and denied.status == 403

    got, denied = _gm_only_inst(
        FakeRequest(app, **{"user_id": "other_session", "owner_authenticated": True}), gk,
    )
    assert denied is None
    assert got is inst

    got, denied = _gm_only_inst(FakeRequest(app, **{"user_id": "gm_session"}), gk)
    assert denied is None
    assert got is inst
