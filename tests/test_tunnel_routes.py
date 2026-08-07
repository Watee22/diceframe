"""隧道路由契约测试：publish/release 插件 token 鉴权、无权限 403、GET 需 owner。

400 校验（非 https 拒绝）由 tests/test_tunnel_service.py 覆盖，这里聚焦鉴权契约。
publish 用真实 HTTP（TestClient）验证 JSON body 解析；status 用 make_mocked_request。
"""

from __future__ import annotations

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request

from src.webui.routes.tunnel import api_tunnel_status, register_tunnel


class FakeAPI:
    def __init__(self) -> None:
        self.published_urls: list[tuple[str, str]] = []

    def authenticate_plugin_token(self, token: str) -> dict | None:
        if token == "good-token":
            return {"plugin_id": "cloudflare-tunnel", "permissions": ["tunnel.publish"]}
        if token == "no-perm-token":
            return {"plugin_id": "other", "permissions": []}
        return None

    def publish_tunnel_url(self, plugin_id: str, url: str) -> dict:
        self.published_urls.append((plugin_id, url))
        return {"ok": True, "public_base_url": url}

    def tunnel_status(self) -> dict:
        return {"ok": True, "active": False, "url": "", "providers": []}


def _make_app() -> web.Application:
    app = web.Application()
    app["api"] = FakeAPI()
    register_tunnel(app)
    return app


@pytest.mark.asyncio
async def test_publish_requires_plugin_token():
    async with TestClient(TestServer(_make_app())) as client:
        resp = await client.post("/api/bot/tunnel/publish", json={"url": "https://abc.trycloudflare.com"})
        assert resp.status == 401


@pytest.mark.asyncio
async def test_publish_rejects_invalid_token():
    async with TestClient(TestServer(_make_app())) as client:
        resp = await client.post(
            "/api/bot/tunnel/publish", json={"url": "https://abc.trycloudflare.com"},
            headers={"X-Bot-Token": "bad-token"},
        )
        assert resp.status == 401


@pytest.mark.asyncio
async def test_publish_rejects_plugin_without_permission():
    async with TestClient(TestServer(_make_app())) as client:
        resp = await client.post(
            "/api/bot/tunnel/publish", json={"url": "https://abc.trycloudflare.com"},
            headers={"X-Bot-Token": "no-perm-token"},
        )
        assert resp.status == 403


@pytest.mark.asyncio
async def test_publish_success():
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/bot/tunnel/publish", json={"url": "https://abc.trycloudflare.com"},
            headers={"X-Bot-Token": "good-token"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert app["api"].published_urls == [("cloudflare-tunnel", "https://abc.trycloudflare.com")]


@pytest.mark.asyncio
async def test_status_requires_owner():
    request = make_mocked_request("GET", "/api/system/tunnel", app=_make_app())
    resp = await api_tunnel_status(request)
    assert resp.status == 403


@pytest.mark.asyncio
async def test_status_owner_ok():
    request = make_mocked_request("GET", "/api/system/tunnel", app=_make_app())
    request["owner_authenticated"] = True
    resp = await api_tunnel_status(request)
    assert resp.status == 200
