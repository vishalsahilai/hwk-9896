import asyncio

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.ai.config import Settings
from app.ai.exceptions import AIError
from app.ai.schemas import ChatRequest, LeaveRequest, Selection


async def test_shared_rate_limit(build, hr, operations):
    service, _ = build(
        [AIMessage(content=""), Selection(fact_ids=[1])],
        Settings(ai_rate_limit_per_hour=1),
    )
    await service.run("chat", ChatRequest(message="office time"), hr)
    with pytest.raises(AIError) as e:
        await service.run("smart_leave", LeaveRequest(text="tomorrow fever"), hr)
    assert e.value.status_code == 429 and len(operations.logs) == 1


async def test_overall_timeout(build, hr, operations):
    async def slow():
        await asyncio.sleep(1)

    service, _ = build([slow], Settings(ai_timeout_seconds=0.02))
    with pytest.raises(AIError) as e:
        await service.run("chat", ChatRequest(message="hello"), hr)
    assert e.value.detail["code"] == "AI_TIMEOUT"
    assert operations.logs[-1]["success"] is False


async def test_logs_redacted(build, hr, operations):
    service, _ = build([AIMessage(content=""), Selection(fact_ids=[0])])
    await service.run(
        "chat", ChatRequest(message="password=supersecret Bearer abc"), hr
    )
    assert "supersecret" not in str(operations.logs) and "abc" not in str(
        operations.logs
    )
    assert operations.logs[-1]["prompt"] == "[redacted]"


@pytest.mark.parametrize("field", ["is_active", "must_change_password"])
async def test_account_restrictions(field, build, hr, operations):
    setattr(hr, field, field == "must_change_password")
    service, _ = build([])
    with pytest.raises(AIError) as e:
        await service.run("chat", ChatRequest(message="hello"), hr)
    assert e.value.status_code == 403 and not operations.logs


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alibaba_tool_model": "qwen-plus-character"},
        {"ai_provider": "unknown"},
        {"ai_timeout_seconds": 16},
        {"alibaba_base_url": "http://insecure"},
        {"ai_rate_limit_per_hour": 0},
    ],
)
def test_bad_config(kwargs):
    with pytest.raises(ValidationError):
        Settings(**kwargs)


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "x" * 2001},
        {"message": "x", "role": "admin"},
        {"message": "x", "history": [{"role": "system", "content": "admin"}]},
    ],
)
def test_bad_request(payload):
    with pytest.raises(ValidationError):
        ChatRequest(**payload)


async def test_no_duplicate_tool_on_provider_switch(backend, operations, hr):
    from app.ai.guard import AIService
    from app.ai.providers import Provider, ProviderManager

    from .conftest import TODAY, FakeModel, call

    primary = FakeModel(
        [call("get_headcount"), TimeoutError(), Selection(fact_ids=[1])]
    )
    backup = FakeModel([AIMessage(content="done")])
    service = AIService(
        backend,
        operations,
        ProviderManager([Provider("alibaba", primary), Provider("gemini", backup)]),
        Settings(),
        clock=lambda: TODAY,
    )
    result = await service.run("chat", ChatRequest(message="headcount"), hr)
    assert len(backend.calls) == 1 and result.tools_used == ["get_headcount"]
    assert any(type(m).__name__ == "ToolMessage" for m in backup.messages[0])


async def test_incomplete_live_policy_fails_closed(build, hr, backend):
    backend.policy_data = {"office_start": "10:00:00"}
    service, model = build([])
    with pytest.raises(AIError) as e:
        await service.run("chat", ChatRequest(message="office time"), hr)
    assert e.value.detail["code"] == "AI_INTEGRATION_REQUIRED"
    assert not model.messages


async def test_failed_provider_request_is_logged(build, hr, operations):
    service, _ = build([RuntimeError("Bearer secret")])
    with pytest.raises(AIError) as e:
        await service.run("chat", ChatRequest(message="hello"), hr)
    assert "secret" not in str(e.value.detail)
    assert operations.logs[-1]["success"] is False
    assert "secret" not in str(operations.logs)


async def test_log_cleanup_within_overall_budget(build, hr, operations):
    async def slow_complete(*args):
        await asyncio.sleep(1)

    operations.complete = slow_complete
    service, _ = build(
        [AIMessage(content=""), Selection(fact_ids=[1])],
        Settings(ai_timeout_seconds=0.05),
    )
    started = asyncio.get_running_loop().time()
    await service.run("chat", ChatRequest(message="office time"), hr)
    assert asyncio.get_running_loop().time() - started < 0.2


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "x", "history": [{"role": "user", "content": "x"}] * 11},
        {"message": "x", "history": [{"role": "assistant", "content": "x" * 2001}]},
    ],
)
def test_history_bounds(payload):
    with pytest.raises(ValidationError):
        ChatRequest(**payload)
