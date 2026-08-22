from __future__ import annotations

import json

import pytest

from src.asr import AsrServiceError
from src.webui.routes import asr


class _FakeApi:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls = []

    async def transcribe_speech(self, game_key, user_id, audio, content_type, language, owner=False):
        self.calls.append((game_key, user_id, audio, content_type, language))
        if self.error:
            raise self.error
        return {"ok": True, "text": "推开石门", "provider": "openai-compatible", "model": "whisper-1"}

    async def test_transcription(self, audio, content_type, language):
        self.calls.append(("", audio, content_type, language))
        if self.error:
            raise self.error
        return {"ok": True, "text": "测试识别", "provider": "openai-compatible", "model": "whisper-1"}


class _Request:
    def __init__(self, api, *, user_id="player"):
        self.app = {"api": api}
        self.match_info = {"game_key": "web|room|bot"}
        self._body = b"clip"
        self.headers = {"Content-Type": "audio/webm;codecs=opus"}
        self.query = {"lang": "zh-CN"}
        self._user_id = user_id

    def get(self, key, default=None):
        return self._user_id if key == "user_id" else default

    async def read(self):
        return self._body


@pytest.mark.asyncio
async def test_game_transcription_route_returns_text():
    api = _FakeApi()

    response = await asr.api_game_transcription(_Request(api))

    assert response.status == 200
    assert json.loads(response.text)["text"] == "推开石门"
    assert api.calls == [("web|room|bot", "player", b"clip", "audio/webm", "zh-CN")]


@pytest.mark.asyncio
async def test_game_transcription_route_maps_service_errors():
    forbidden = await asr.api_game_transcription(_Request(_FakeApi(error=PermissionError("当前身份不属于本局游戏"))))
    assert forbidden.status == 403

    bad_request = await asr.api_game_transcription(_Request(_FakeApi(error=AsrServiceError("录音内容为空"))))
    assert bad_request.status == 400

    missing = await asr.api_game_transcription(_Request(_FakeApi(error=KeyError("游戏不存在"))))
    assert missing.status == 404


@pytest.mark.asyncio
async def test_asr_test_route_returns_text_for_owner():
    api = _FakeApi()

    response = await asr.api_test_transcription(_Request(api, user_id=""))

    assert response.status == 200
    assert json.loads(response.text)["text"] == "测试识别"
    assert api.calls == [("", b"clip", "audio/webm", "zh-CN")]


@pytest.mark.asyncio
async def test_player_share_cannot_use_asr_test():
    request = _Request(_FakeApi())
    request.query = {"user": "player", "lang": "zh-CN"}

    response = await asr.api_test_transcription(request)

    assert response.status == 403
    assert "分享页" in json.loads(response.text)["error"]
