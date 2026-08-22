from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.llm.client import (
    LLMClient,
    OutputTruncatedError,
    ProviderConfig,
    length_retry_budgets,
)


def test_length_retry_budgets_are_shared_one_two_four_times():
    assert length_retry_budgets(2048) == (2048, 4096, 8192)


class _FakeResponse:
    status = 200
    headers = {}
    request_info = None
    history = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return {
            "content": [{"type": "text", "text": "OK"}],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }

    async def text(self):
        return ""


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _FakeResponse()


class _EmptyOpenAIResponse(_FakeResponse):
    async def json(self):
        return {
            "choices": [{
                "message": {
                    "content": "",
                    "reasoning_content": "首先，任务是压缩给定的 TRPG GM 正文，只输出压缩后的正文。",
                },
                "finish_reason": "length",
            }],
            "usage": {"total_tokens": 512},
        }


class _PartialOpenAIResponse(_FakeResponse):
    async def json(self):
        return {
            "choices": [{
                "message": {"content": "已经生成但没有结束的部分正文"},
                "finish_reason": "length",
            }],
            "usage": {"total_tokens": 512},
        }


class _EmptyOpenAISession(_FakeSession):
    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _EmptyOpenAIResponse()


class _PartialOpenAISession(_FakeSession):
    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _PartialOpenAIResponse()


class _CompleteOpenAIResponse(_FakeResponse):
    async def json(self):
        return {
            "choices": [{
                "message": {"content": "完整正文。"},
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 640},
        }


class _ToolOpenAIResponse(_FakeResponse):
    async def json(self):
        return {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "dice_checks",
                            "arguments": json.dumps({"checks": [{"player": "p1", "attribute": "str", "target": 12}]}),
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"total_tokens": 29},
        }


class _ToolOpenAISession(_FakeSession):
    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _ToolOpenAIResponse()


class _LengthThenCompleteSession(_FakeSession):
    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if len(self.calls) == 1:
            return _PartialOpenAIResponse()
        return _CompleteOpenAIResponse()


@pytest.mark.asyncio
async def test_anthropic_provider_uses_messages_api(monkeypatch):
    session = _FakeSession()
    client = LLMClient(
        providers=[
            ProviderConfig(
                provider_name="claude",
                base_url="https://api.anthropic.com",
                api_key="test-key",
                model_name="claude-test",
                api_format="anthropic",
            )
        ],
        default="claude",
    )

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    response = await client.call("system prompt", "hello", max_tokens=12, json_mode=True)

    assert response.content == "OK"
    assert response.total_tokens == 5
    call = session.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "test-key"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["json"]["model"] == "claude-test"
    assert call["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert "temperature" not in call["json"]
    assert "system prompt" in call["json"]["system"]
    assert "Return only valid JSON" in call["json"]["system"]


@pytest.mark.asyncio
async def test_openai_provider_never_exposes_reasoning_as_final_content(monkeypatch):
    session = _EmptyOpenAISession()
    provider = ProviderConfig(
        provider_name="reasoning-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="reasoning-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    with pytest.raises(ValueError, match=r"finish_reason=length"):
        await client._call_openai_compatible(
            provider,
            "compress the narration",
            "original narration",
            temperature=0.2,
            max_tokens=512,
        )


@pytest.mark.asyncio
async def test_openai_provider_rejects_partial_content_when_finish_reason_is_length(monkeypatch):
    session = _PartialOpenAISession()
    provider = ProviderConfig(
        provider_name="partial-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="partial-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    with pytest.raises(OutputTruncatedError, match=r"finish_reason=length"):
        await client._call_openai_compatible(
            provider,
            "system",
            "user",
            temperature=0.7,
            max_tokens=512,
        )


@pytest.mark.asyncio
async def test_length_truncation_retries_with_larger_max_tokens(monkeypatch):
    """finish_reason=length 时，call() 应逐步放大 max_tokens 重试，而非用相同预算原地重试。"""
    session = _EmptyOpenAISession()
    provider = ProviderConfig(
        provider_name="reasoning-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="reasoning-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    monkeypatch.setattr("src.llm.client.BASE_DELAY", 0.0)

    with pytest.raises(RuntimeError):
        await client.call("system", "user", max_tokens=512)

    # 3 次尝试的 max_tokens 应为 512 -> 1024 -> 2048（2x 步进，4x 上限）
    sent_budgets = [call["json"]["max_tokens"] for call in session.calls]
    assert sent_budgets == [512, 1024, 2048]


@pytest.mark.asyncio
async def test_length_retry_reports_initial_and_successful_token_budgets(monkeypatch):
    session = _LengthThenCompleteSession()
    provider = ProviderConfig(
        provider_name="reasoning-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="reasoning-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    monkeypatch.setattr("src.llm.client.BASE_DELAY", 0.0)

    response = await client.call("system", "user", max_tokens=512)

    assert response.narration == "完整正文。"
    assert response.token_budget_initial == 512
    assert response.token_budget_used == 1024


@pytest.mark.asyncio
async def test_call_tools_uses_native_openai_function_calling(monkeypatch):
    session = _ToolOpenAISession()
    provider = ProviderConfig(
        provider_name="tool-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="tool-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    tool = {
        "type": "function",
        "function": {
            "name": "dice_checks",
            "description": "plan checks",
            "parameters": {"type": "object", "properties": {"checks": {"type": "array"}}},
        },
    }
    result = await client.call_tools("system", "actions", tools=[tool])
    assert result.native_tools is True
    assert result.total_tokens == 29
    assert result.tool_calls == [{
        "name": "dice_checks",
        "arguments": {"checks": [{"player": "p1", "attribute": "str", "target": 12}]},
    }]
    body = session.calls[0]["json"]
    assert body["tools"] == [tool]
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": "dice_checks"},
    }
    assert "thinking" not in body


@pytest.mark.asyncio
async def test_official_deepseek_v4_disables_thinking_for_tool_calls(monkeypatch):
    session = _ToolOpenAISession()
    provider = ProviderConfig(
        provider_name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model_name="deepseek-v4-flash",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    await client.call_tools("system", "actions", tools=[_DICE_TOOL])

    body = session.calls[0]["json"]
    assert body["thinking"] == {"type": "disabled"}
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": "dice_checks"},
    }


@pytest.mark.asyncio
async def test_official_deepseek_v4_disables_thinking_for_json_mode(monkeypatch):
    session = _SequentialSession([_CompleteOpenAIResponse()])
    provider = ProviderConfig(
        provider_name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model_name="deepseek-v4-pro",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    await client._call_openai_compatible(
        provider,
        "system",
        "user",
        temperature=0.1,
        max_tokens=128,
        json_mode=True,
    )

    body = session.calls[0]["json"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}


class _ErrorOpenAIResponse(_FakeResponse):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self._message = message
        self.headers = {}
        self.request_info = SimpleNamespace(
            real_url="https://test.local/v1/chat/completions",
            url="https://test.local/v1/chat/completions",
            method="POST",
            headers={},
        )
        self.history = ()

    async def text(self):
        return self._message


class _JSONContentOpenAIResponse(_FakeResponse):
    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def json(self):
        return {
            "choices": [{
                "message": {"content": self._payload},
                "finish_reason": "stop",
            }],
            "usage": {"total_tokens": 300},
        }


class _SequentialSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


_DICE_TOOL = {
    "type": "function",
    "function": {
        "name": "dice_checks",
        "description": "plan checks",
        "parameters": {"type": "object", "properties": {"checks": {"type": "array"}}},
    },
}


@pytest.mark.asyncio
async def test_call_tools_retries_with_auto_tool_choice_when_forced_rejected(monkeypatch):
    """思考模式模型拒绝强制 tool_choice 时，应改用 auto 重试原生调用而非直接回退。"""
    session = _SequentialSession([
        _ErrorOpenAIResponse(400, '{"error":{"message":"Thinking mode does not support this tool_choice"}}'),
        _ToolOpenAIResponse(),
    ])
    provider = ProviderConfig(
        provider_name="thinking-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="thinking-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    result = await client.call_tools("system", "actions", tools=[_DICE_TOOL])

    assert result.native_tools is True
    assert result.provider_used == "thinking-model"
    assert session.calls[0]["json"]["tool_choice"] == {
        "type": "function",
        "function": {"name": "dice_checks"},
    }
    assert session.calls[1]["json"]["tool_choice"] == "auto"
    # 供应商被记住：后续调用直接走 auto，不再触发 400
    assert provider.provider_name in client._native_tool_auto
    assert provider.provider_name in client._native_tool_unsupported
    follow_up = _ToolOpenAISession()

    async def fake_get_session2():
        return follow_up

    monkeypatch.setattr(client, "_get_session", fake_get_session2)
    result2 = await client.call_tools("system", "actions", tools=[_DICE_TOOL])
    assert result2.native_tools is True
    assert len(follow_up.calls) == 1
    assert follow_up.calls[0]["json"]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_call_tools_json_fallback_retries_with_larger_max_tokens(monkeypatch):
    """JSON 回退截断时应按预算序列放大 max_tokens 重试，而非一次失败即放弃。"""
    json_payload = json.dumps(
        {"tool_calls": [{"name": "dice_checks", "arguments": {"checks": []}}]},
        ensure_ascii=False,
    )
    session = _SequentialSession([
        _EmptyOpenAIResponse(),                       # 思考烧完预算 -> finish_reason=length
        _JSONContentOpenAIResponse(json_payload),     # 放大后成功
    ])
    provider = ProviderConfig(
        provider_name="thinking-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="thinking-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)
    client._native_tool_unsupported.add(provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    monkeypatch.setattr("src.llm.client.BASE_DELAY", 0.0)

    result = await client.call_tools("system", "actions", tools=[_DICE_TOOL], max_tokens=512)

    assert result.native_tools is False
    assert result.tool_calls == [{"name": "dice_checks", "arguments": {"checks": []}}]
    sent_budgets = [call["json"]["max_tokens"] for call in session.calls]
    assert sent_budgets == [512, 1024]


@pytest.mark.asyncio
async def test_call_tools_json_fallback_raises_after_exhausted_budgets(monkeypatch):
    """所有预算档位均截断时 JSON 回退应失败，由上层进入离线路径。"""
    session = _SequentialSession([
        _EmptyOpenAIResponse(),
        _EmptyOpenAIResponse(),
        _EmptyOpenAIResponse(),
    ])
    provider = ProviderConfig(
        provider_name="thinking-model",
        base_url="https://api.example.com",
        api_key="test-key",
        model_name="thinking-test",
    )
    client = LLMClient(providers=[provider], default=provider.provider_name)
    client._native_tool_unsupported.add(provider.provider_name)

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)
    monkeypatch.setattr("src.llm.client.BASE_DELAY", 0.0)

    with pytest.raises(RuntimeError, match="所有模型工具调用均失败"):
        await client.call_tools("system", "actions", tools=[_DICE_TOOL], max_tokens=512)
    sent_budgets = [call["json"]["max_tokens"] for call in session.calls]
    assert sent_budgets == [512, 1024, 2048]


class _FakeStreamContent:
    """模拟 aiohttp StreamReader 的按行异步迭代（每行含 \\n）。"""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._i]
        self._i += 1
        return line


class _FakeStreamResponse:
    def __init__(self, lines: list[bytes], status: int = 200) -> None:
        self.status = status
        self.headers = {}
        # aiohttp ClientResponseError.__str__ 会读 request_info.real_url，给个最小占位避免格式化报错
        self.request_info = SimpleNamespace(real_url="https://test.local/v1", url="https://test.local/v1", method="POST", headers={})
        self.history = ()
        self.content = _FakeStreamContent(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return "error body"


class _FakeStreamSession:
    def __init__(self, lines: list[bytes], status: int = 200) -> None:
        self.lines = lines
        self.status = status
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _FakeStreamResponse(self.lines, status=self.status)


class _SequentialStreamSession:
    """按顺序返回不同响应，用于测 provider fallback。"""

    def __init__(self, responses: list[_FakeStreamResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _openai_sse_lines(deltas: list[tuple[str, str]]) -> list[bytes]:
    """构造 OpenAI 流式 SSE：deltas = [(content, finish_reason), ...]，最后附 usage 与 [DONE]。"""
    lines: list[bytes] = []
    for content, finish in deltas:
        delta_obj = {"content": content} if content is not None else {}
        choice: dict = {"delta": delta_obj}
        if finish:
            choice["finish_reason"] = finish
        lines.append(("data: " + json.dumps({"choices": [choice]}) + "\n").encode())
    lines.append(b'data: {"usage":{"total_tokens":42}}\n')
    lines.append(b"data: [DONE]\n")
    return lines


@pytest.mark.asyncio
async def test_call_stream_openai_yields_deltas_and_returns_response(monkeypatch):
    session = _FakeStreamSession(_openai_sse_lines([("Hello", ""), (", ", ""), ("world!", "stop")]))
    provider = ProviderConfig(
        provider_name="openai",
        base_url="https://api.example.com",
        api_key="k",
        model_name="m",
    )
    client = LLMClient(providers=[provider], default="openai")

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    deltas: list[str] = []

    async def on_delta(text):
        deltas.append(text)

    response = await client.call_stream("system", "hello", max_tokens=64, on_delta=on_delta)

    assert deltas == ["Hello", ", ", "world!"]
    assert response.content == "Hello, world!"
    assert response.total_tokens == 42
    assert response.provider_used == "openai"
    body = session.calls[0]["json"]
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_call_stream_anthropic_yields_deltas_and_returns_response(monkeypatch):
    lines = [
        b'event: message_start\n',
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":5}}}\n',
        b'event: content_block_delta\n',
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi "}}\n',
        b'event: content_block_delta\n',
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"there"}}\n',
        b'event: message_delta\n',
        b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}\n',
        b'event: message_stop\n',
        b'data: {"type":"message_stop"}\n',
    ]
    session = _FakeStreamSession(lines)
    provider = ProviderConfig(
        provider_name="claude",
        base_url="https://api.anthropic.com",
        api_key="k",
        model_name="claude-test",
        api_format="anthropic",
    )
    client = LLMClient(providers=[provider], default="claude")

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    deltas: list[str] = []

    async def on_delta(text):
        deltas.append(text)

    response = await client.call_stream("system", "hello", max_tokens=64, on_delta=on_delta)

    assert deltas == ["Hi ", "there"]
    assert response.content == "Hi there"
    assert response.total_tokens == 8
    assert response.provider_used == "claude"
    assert session.calls[0]["json"]["stream"] is True


@pytest.mark.asyncio
async def test_call_stream_openai_length_truncation_raises(monkeypatch):
    session = _FakeStreamSession(_openai_sse_lines([("", "length")]))
    provider = ProviderConfig(
        provider_name="reasoning-model",
        base_url="https://api.example.com",
        api_key="k",
        model_name="m",
    )
    client = LLMClient(providers=[provider], default="reasoning-model")

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    with pytest.raises(OutputTruncatedError):
        await client.call_stream("system", "hello", max_tokens=512)


@pytest.mark.asyncio
async def test_call_stream_openai_partial_length_truncation_raises(monkeypatch):
    session = _FakeStreamSession(
        _openai_sse_lines([("部分正文", ""), ("", "length")])
    )
    provider = ProviderConfig(
        provider_name="reasoning-model",
        base_url="https://api.example.com",
        api_key="k",
        model_name="m",
    )
    client = LLMClient(providers=[provider], default="reasoning-model")

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    deltas: list[str] = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    with pytest.raises(OutputTruncatedError):
        await client.call_stream(
            "system",
            "hello",
            max_tokens=512,
            on_delta=on_delta,
        )

    assert deltas == ["部分正文"]


@pytest.mark.asyncio
async def test_call_stream_falls_back_to_next_provider(monkeypatch):
    """主供应商 HTTP 500（不可重试）时，应跳到 fallback 供应商完成流式。"""
    primary = ProviderConfig(
        provider_name="primary",
        base_url="https://api.example.com",
        api_key="k",
        model_name="m",
    )
    fallback = ProviderConfig(
        provider_name="backup",
        base_url="https://api.backup.com",
        api_key="k",
        model_name="m",
        fallback=True,
    )
    client = LLMClient(providers=[primary, fallback], default="primary")

    session = _SequentialStreamSession([
        _FakeStreamResponse([], status=500),  # 主供应商失败
        _FakeStreamResponse(_openai_sse_lines([("ok", "stop")])),  # fallback 成功
    ])

    async def fake_get_session():
        return session

    monkeypatch.setattr(client, "_get_session", fake_get_session)

    deltas: list[str] = []

    async def on_delta(text):
        deltas.append(text)

    response = await client.call_stream("system", "hello", max_tokens=64, on_delta=on_delta)

    assert deltas == ["ok"]
    assert response.content == "ok"
    assert response.provider_used == "backup"
    assert len(session.calls) == 2
    assert session.calls[0]["url"].startswith("https://api.example.com")
    assert session.calls[1]["url"].startswith("https://api.backup.com")
