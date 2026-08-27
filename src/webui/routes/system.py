"""System metadata routes."""

from __future__ import annotations

from aiohttp import web

from src.webui.routes._common import _get_api, _require_confirmed_request


async def api_update_check(request: web.Request) -> web.Response:
    raw = request.query.get("prerelease")
    override = raw.strip().lower() in {"1", "true", "yes"} if raw is not None else None
    return web.json_response(await _get_api(request).check_updates(override))


async def api_runtime_log_status(request: web.Request) -> web.Response:
    return web.json_response(_get_api(request).runtime_log_status())


async def api_clear_runtime_logs(request: web.Request) -> web.Response:
    if denied := _require_confirmed_request(request):
        return denied
    return web.json_response(_get_api(request).clear_runtime_logs())


def register_system(app: web.Application) -> None:
    app.router.add_get("/api/system/update-check", api_update_check)
    app.router.add_get("/api/system/runtime-logs", api_runtime_log_status)
    app.router.add_post("/api/system/runtime-logs/clear", api_clear_runtime_logs)
