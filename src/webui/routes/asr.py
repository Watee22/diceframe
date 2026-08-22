"""HTTP endpoints for cloud speech-to-text."""

from __future__ import annotations

from aiohttp import web

from src.asr import AsrServiceError
from src.webui.routes._common import _get_api
from src.webui.routes.auth import ACCESS_PASSWORD_CONFIGURED_KEY


async def api_game_transcription(request: web.Request) -> web.Response:
    return await _transcribe(request, game_key=request.match_info["game_key"])


async def api_test_transcription(request: web.Request) -> web.Response:
    denied = _require_asr_admin(request)
    if denied is not None:
        return denied
    return await _transcribe(request)


def _require_asr_admin(request: web.Request) -> web.Response | None:
    query = getattr(request, "query", {})
    if query.get("user") or query.get("share"):
        return web.json_response({"ok": False, "error": "玩家分享页不可使用语音识别测试"}, status=403)
    if request.get(ACCESS_PASSWORD_CONFIGURED_KEY, False) and not request.get("owner_authenticated", False):
        return web.json_response({"ok": False, "error": "仅管理员可以测试语音识别"}, status=403)
    return None


async def _transcribe(request: web.Request, game_key: str = "") -> web.Response:
    audio = await request.read()
    content_type = str(request.headers.get("Content-Type") or "").split(";", 1)[0].strip() or "audio/webm"
    language = str(request.query.get("lang") or "").strip()
    api = _get_api(request)
    try:
        if game_key:
            result = await api.transcribe_speech(
                game_key,
                request.get("user_id", ""),
                audio,
                content_type,
                language,
                owner=bool(request.get("owner_authenticated", False)),
            )
        else:
            result = await api.test_transcription(audio, content_type, language)
    except KeyError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    except PermissionError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=403)
    except (AsrServiceError, ValueError) as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(result)


def register_asr(app: web.Application) -> None:
    app.router.add_post("/api/games/{game_key}/transcription", api_game_transcription)
    app.router.add_post("/api/asr/test", api_test_transcription)
