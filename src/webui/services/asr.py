"""WebUI ASR domain: membership checks and transcription delegation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.asr import TranscriptionRequest

if TYPE_CHECKING:
    from src.webui.api import WebAPI


async def transcribe(
    api: "WebAPI",
    game_key: str,
    user_id: str,
    audio: bytes,
    content_type: str,
    language: str = "",
    owner: bool = False,
) -> dict[str, Any]:
    inst = api._reg.get(api._parse_key(game_key))
    if inst is None:
        raise KeyError("游戏不存在")
    if not user_id or not (owner or user_id == inst.gm_uid or user_id in inst.players):
        raise PermissionError("当前身份不属于本局游戏")
    result = await api._asr.transcribe(
        TranscriptionRequest(audio=audio, content_type=content_type, language=language),
    )
    return {"ok": True, **result.public_dict()}


async def test_transcription(
    api: "WebAPI",
    audio: bytes,
    content_type: str,
    language: str = "",
) -> dict[str, Any]:
    result = await api._asr.transcribe(
        TranscriptionRequest(audio=audio, content_type=content_type, language=language),
    )
    return {"ok": True, **result.public_dict()}
