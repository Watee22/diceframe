from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.webui.routes import assistant as assistant_routes
from src.webui.services import assistant as assistant_service


class FakeLLMClient:
    def __init__(self, deltas=None, error=None):
        self.deltas = deltas or ["你", "好"]
        self.error = error
        self.calls = []

    async def call_stream(self, system_prompt, user_message, *, temperature=0.7, max_tokens=1024,
                          force_provider=None, json_mode=False, on_delta=None):
        self.calls.append({"system": system_prompt, "user": user_message})
        if self.error:
            raise self.error
        for d in self.deltas:
            await on_delta(d)


class FakeAPI:
    def __init__(self, plugins=None, llm_client=None, config_error=None, data_dir: Path | None = None):
        self._plugins = plugins
        self._llm_client = llm_client
        self._config_error = config_error
        self._reg = SimpleNamespace(save_dir=(data_dir or Path("data")) / "saves")
        self.text_gen_max_tokens = 1024

    def list_plugins(self):
        return {"plugins": [{
            "id": "cloudflare-tunnel",
            "name": "隧道",
            "plugin_type": "tool",
            "version": "1.0.0",
            "enabled": True,
            "running": True,
            "description": "外网接入",
        }]}

    def _llm_configuration_error(self, language):
        return self._config_error


class FakeStreamResponse:
    def __init__(self):
        self.written = []

    async def write(self, data: bytes):
        self.written.append(data)


# ---- _system_prompt ----

def test_system_prompt_includes_plugins():
    api = FakeAPI()
    text = assistant_service._system_prompt(api, "zh-CN")
    assert "官方文档助手" in text
    assert "隧道" in text
    assert "当前实例已安装插件" in text
    assert "plugin_type" not in text


def test_system_prompt_language_en():
    api = FakeAPI()
    text = assistant_service._system_prompt(api, "en")
    assert "Official Documentation Assistant" in text


def test_system_prompt_omits_plugins_for_unrelated_question():
    api = FakeAPI()
    text = assistant_service._system_prompt(api, "zh-CN", query="怎么配置模型 API")
    assert "本题不需要插件清单" in text
    assert "cloudflare-tunnel" not in text


def test_system_prompt_includes_plugins_for_plugin_question():
    api = FakeAPI()
    text = assistant_service._system_prompt(api, "zh-CN", query="cloudflare-tunnel 插件怎么用")
    assert "cloudflare-tunnel" in text


# ---- _build_user_message ----

def test_build_user_message_single():
    assert assistant_service._build_user_message([{"role": "user", "content": "怎么配置API"}]) == "怎么配置API"


def test_build_user_message_with_history():
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好!"},
        {"role": "user", "content": "怎么创建角色"},
    ]
    result = assistant_service._build_user_message(messages)
    assert "用户: 你好" in result
    assert "助手: 你好!" in result
    assert "用户最新问题: 怎么创建角色" in result


def test_build_user_message_empty():
    assert assistant_service._build_user_message([]) == ""


def test_log_diagnosis_requires_explicit_runtime_log_intent():
    assert assistant_service._wants_runtime_log_context("检查运行日志，帮我找问题") is True
    assert assistant_service._wants_runtime_log_context("怎么查看剧情日志") is False


# ---- chat_stream ----

@pytest.mark.asyncio
async def test_chat_stream_llm_not_configured():
    api = FakeAPI(config_error={"error": "尚未配置模型 API"})
    resp = FakeStreamResponse()
    await assistant_service.chat_stream(api, resp, [{"role": "user", "content": "hi"}], "zh-CN")
    text = b"".join(resp.written).decode()
    assert "event: error" not in text
    assert "DiceFrame 自带的离线回复" in text
    assert "设置 > 模型接口" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_chat_stream_offline_model_setup_guide():
    api = FakeAPI(config_error={"error": "尚未配置模型 API"})
    resp = FakeStreamResponse()
    await assistant_service.chat_stream(
        api,
        resp,
        [{"role": "user", "content": "怎样配置模型 API？"}],
        "zh-CN",
    )
    text = b"".join(resp.written).decode()
    assert "event: error" not in text
    assert "不会调用外部模型" in text
    assert "Base URL" in text
    assert "测试连接" in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_chat_stream_deltas_and_done():
    api = FakeAPI(llm_client=FakeLLMClient(deltas=["你", "好"]))
    resp = FakeStreamResponse()
    await assistant_service.chat_stream(api, resp, [{"role": "user", "content": "怎么配置 API"}], "zh-CN")
    text = b"".join(resp.written).decode()
    assert "event: sources" in text
    assert '"delta": "你"' in text
    assert '"delta": "好"' in text
    assert "event: done" in text


@pytest.mark.asyncio
async def test_chat_stream_sends_only_redacted_log_context_to_model(monkeypatch, tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("TRPG_LOG_DIR", str(log_dir))
    (log_dir / "diceframe.log").write_text(
        'WARNING api_key="sk-private" model rejected DeepSeek-V4\n',
        encoding="utf-8",
    )
    client = FakeLLMClient(deltas=["请修改模型名称"])
    api = FakeAPI(llm_client=client, data_dir=tmp_path / "data")
    resp = FakeStreamResponse()

    await assistant_service.chat_stream(
        api,
        resp,
        [{"role": "user", "content": "检查运行日志，帮我找出问题"}],
        "zh-CN",
    )

    system = client.calls[0]["system"]
    assert "运行日志（已脱敏" in system
    assert "model rejected DeepSeek-V4" in system
    assert "sk-private" not in system
    assert "[REDACTED]" in system
    response_text = b"".join(resp.written).decode()
    assert "DiceFrame 运行日志（已脱敏）" in response_text


@pytest.mark.asyncio
async def test_chat_stream_error_event():
    api = FakeAPI(llm_client=FakeLLMClient(error=RuntimeError("boom")))
    resp = FakeStreamResponse()
    await assistant_service.chat_stream(api, resp, [{"role": "user", "content": "x"}], "zh-CN")
    text = b"".join(resp.written).decode()
    assert "event: error" in text


@pytest.mark.asyncio
async def test_chat_stream_truncation_retries_with_reset():
    """输出被 max_tokens 截断时应发 reset 并放大预算重试，而非直接报错。"""
    from src.llm.client import OutputTruncatedError

    class RetryClient:
        def __init__(self):
            self.attempts = 0
            self.max_tokens_seen: list[int] = []

        async def call_stream(self, system_prompt, user_message, *, temperature=0.7,
                              max_tokens=1024, force_provider=None, json_mode=False, on_delta=None):
            self.attempts += 1
            self.max_tokens_seen.append(max_tokens)
            if self.attempts == 1:
                raise OutputTruncatedError("length")
            await on_delta("完整回答")

    api = FakeAPI(llm_client=RetryClient())
    resp = FakeStreamResponse()
    await assistant_service.chat_stream(api, resp, [{"role": "user", "content": "问题"}], "zh-CN")

    text = b"".join(resp.written).decode()
    assert "event: reset" in text
    assert '"delta": "完整回答"' in text
    assert "event: done" in text
    assert "event: error" not in text
    # length_retry_budgets(1024) = 1024 -> 2048；第二次预算放大后成功
    assert api._llm_client.max_tokens_seen == [1024, 2048]


# ---- route ----

def _make_request(owner=False):
    class FakeRequest:
        def __init__(self):
            self.headers = {}
            self.method = "POST"
            self._owner = owner
            self.app = {"api": SimpleNamespace()}

        def get(self, key, default=None):
            return {"owner_authenticated": self._owner}.get(key, default)

        async def json(self):
            return {"messages": [{"role": "user", "content": "hi"}], "language": "zh-CN"}

    return FakeRequest()


@pytest.mark.asyncio
async def test_route_rejects_non_owner():
    req = _make_request(owner=False)
    resp = await assistant_routes.api_assistant_chat(req)
    assert resp.status == 401
    assert json.loads(resp.text)["error"] == "未授权"


@pytest.mark.asyncio
async def test_route_owner_calls_service(monkeypatch):
    req = _make_request(owner=True)
    called = {"n": 0}

    async def fake_chat(response, messages, language):
        called["n"] += 1

    async def fake_prepare(self, request):
        return None

    req.app["api"] = SimpleNamespace(assistant_chat=fake_chat)
    monkeypatch.setattr(assistant_routes.web.StreamResponse, "prepare", fake_prepare)
    resp = await assistant_routes.api_assistant_chat(req)
    assert resp.status == 200
    assert resp.headers["Content-Type"] == "text/event-stream"
    assert called["n"] == 1


def test_route_message_validation():
    messages, language = assistant_routes._validated_messages({
        "messages": [{"role": "user", "content": "hello"}],
        "language": "en-US",
    })
    assert messages == [{"role": "user", "content": "hello"}]
    assert language == "en"

    messages, _ = assistant_routes._validated_messages({
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "   "},
        ],
    })
    assert messages == [{"role": "user", "content": "hello"}]

    with pytest.raises(ValueError, match="最后一条"):
        assistant_routes._validated_messages({
            "messages": [{"role": "assistant", "content": "hello"}],
        })

    with pytest.raises(ValueError, match="过长"):
        assistant_routes._validated_messages({
            "messages": [{"role": "user", "content": "x" * 8001}],
        })
