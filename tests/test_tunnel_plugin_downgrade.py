"""cloudflare-tunnel 插件降级与解析测试（§10）。

用 mock 的 urlopen 验证：publish 遇 404/403（旧版核心无接缝）降级为 manual 模式、
其他 HTTP 错误抛异常、隧道 URL 正则正确排除 api.trycloudflare.com。
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "cloudflare-tunnel"
sys.path.insert(0, str(_PLUGIN_DIR))

from main import URL_RE, _publish  # noqa: E402


@pytest.fixture
def tunnel_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRPG_API_BASE", "http://127.0.0.1:18000")
    monkeypatch.setenv("TRPG_BOT_TOKEN", "test-token")


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("url", code, "err", None, None)


def test_publish_404_returns_manual_mode(monkeypatch: pytest.MonkeyPatch, tunnel_env):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _raise_http(404))

    result = _publish("https://abc.trycloudflare.com")

    assert result["ok"] is True
    assert result["mode"] == "manual"
    assert "不支持自动写入" in result.get("hint", "")


def test_publish_403_returns_manual_mode(monkeypatch: pytest.MonkeyPatch, tunnel_env):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _raise_http(403))

    result = _publish("https://abc.trycloudflare.com")

    assert result["mode"] == "manual"


def test_publish_other_http_error_raises(monkeypatch: pytest.MonkeyPatch, tunnel_env):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _raise_http(500))

    with pytest.raises(RuntimeError, match="500"):
        _publish("https://abc.trycloudflare.com")


def test_url_re_parses_tunnel_url():
    match = URL_RE.search(
        "Your quick tunnel has been created! "
        "Visit it at https://abc-123.trycloudflare.com now"
    )
    assert match is not None
    assert match.group(0) == "https://abc-123.trycloudflare.com"


def test_url_re_excludes_api_endpoint():
    # api.trycloudflare.com 是注册端点，不是隧道地址
    assert URL_RE.search("https://api.trycloudflare.com") is None


def _raise_http(code: int):
    raise _http_error(code)
