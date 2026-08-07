"""隧道 service 测试：publish 校验、二次替换、release 恢复、非 publisher release、状态。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.webui.services import tunnel


@pytest.fixture
def tunnel_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """构造带 _config_state(内存 STATE) + _save_config(写盘) 的 api。"""
    monkeypatch.setenv("TRPG_DATA_DIR", str(tmp_path))
    state = {"public_base_url": "http://127.0.0.1:18000", "web_port": 18000}
    config_file = tmp_path / "config.json"

    def save_config():
        config_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    api = SimpleNamespace(
        _config_state=state,
        _save_config=save_config,
        list_plugins=lambda: {"plugins": [
            {"id": "cloudflare-tunnel", "name": "隧道", "permissions": ["tunnel.publish"], "running": True},
            {"id": "other", "name": "其他", "permissions": [], "running": False},
        ]},
    )
    return api


def test_publish_validates_https(tunnel_env):
    with pytest.raises(ValueError, match="https"):
        tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "http://not-secure.example")
    with pytest.raises(ValueError, match="https"):
        tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "not-a-url")


def test_publish_writes_public_base_url_and_preserves_prev(tunnel_env):
    result = tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    assert result["ok"] is True
    assert result["public_base_url"] == "https://abc.trycloudflare.com"
    # STATE 同步（问题 A 的核心）+ 持久化写盘
    assert tunnel_env._config_state["public_base_url"] == "https://abc.trycloudflare.com"
    config = json.loads((Path(os.environ["TRPG_DATA_DIR"]) / "config.json").read_text(encoding="utf-8"))
    assert config["public_base_url"] == "https://abc.trycloudflare.com"


def test_publish_second_plugin_rejected(tunnel_env):
    tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    with pytest.raises(ValueError, match="已由插件"):
        tunnel.publish_tunnel_url(tunnel_env, "other", "https://other.trycloudflare.com")


def test_publish_same_plugin_republish_replaces(tunnel_env):
    """同插件二次发布替换 URL，prev_url 不被覆盖。"""
    tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    result = tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://xyz.trycloudflare.com")
    assert result["public_base_url"] == "https://xyz.trycloudflare.com"
    assert tunnel_env._config_state["public_base_url"] == "https://xyz.trycloudflare.com"
    # release 应回到原始地址，而非 abc
    released = tunnel.release_tunnel_url(tunnel_env, "cloudflare-tunnel")
    assert released["restored"] == "http://127.0.0.1:18000"


def test_release_restores_prev_url(tunnel_env):
    tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    result = tunnel.release_tunnel_url(tunnel_env, "cloudflare-tunnel")
    assert result["ok"] is True
    assert result["restored"] == "http://127.0.0.1:18000"
    assert tunnel_env._config_state["public_base_url"] == "http://127.0.0.1:18000"


def test_release_non_publisher_noop(tunnel_env):
    tunnel.publish_tunnel_url(tunnel_env, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    result = tunnel.release_tunnel_url(tunnel_env, "other")
    assert result["ok"] is True
    assert result["released"] is False


def test_status_lists_providers(tunnel_env):
    status = tunnel.tunnel_status(tunnel_env)
    assert status["ok"] is True
    assert status["active"] is False
    ids = [p["plugin_id"] for p in status["providers"]]
    assert ids == ["cloudflare-tunnel"]


def test_publish_takes_over_after_publisher_uninstalled(tmp_path, monkeypatch):
    """旧 publisher 已卸载（幽灵状态）时，新插件发布不被阻塞，且继承其 prev_url。"""
    monkeypatch.setenv("TRPG_DATA_DIR", str(tmp_path))
    state = {"public_base_url": "http://127.0.0.1:18000"}
    config_file = tmp_path / "config.json"

    def save_config():
        config_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    plugins = [
        {"id": "cloudflare-tunnel", "name": "隧道", "permissions": ["tunnel.publish"], "running": True},
    ]
    api = SimpleNamespace(
        _config_state=state,
        _save_config=save_config,
        list_plugins=lambda: {"plugins": list(plugins)},
    )
    tunnel.publish_tunnel_url(api, "cloudflare-tunnel", "https://abc.trycloudflare.com")
    # 模拟 cloudflare-tunnel 被卸载：从已安装列表消失，但 tunnel_state 仍指向它
    plugins.clear()
    # 新插件发布应接管（不再阻塞），且 prev_url 仍是最初地址
    result = tunnel.publish_tunnel_url(api, "other", "https://xyz.trycloudflare.com")
    assert result["public_base_url"] == "https://xyz.trycloudflare.com"
    released = tunnel.release_tunnel_url(api, "other")
    assert released["restored"] == "http://127.0.0.1:18000"
