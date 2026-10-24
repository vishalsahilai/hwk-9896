import asyncio

import pytest
from langchain_core.messages import AIMessage

from app.ai.exceptions import AIError
from app.ai.providers import Provider, ProviderManager

from .conftest import FakeModel


class HTTPError(Exception):
    def __init__(self, status, text="provider failure secret"):
        self.status_code = status
        super().__init__(text)


def deadline():
    return asyncio.get_running_loop().time() + 1


async def test_alibaba_success():
    primary = FakeModel([AIMessage(content="ok")])
    backup = FakeModel([])
    attempts = []
    result = await ProviderManager(
        [Provider("alibaba", primary), Provider("gemini", backup)]
    ).invoke([], deadline(), attempts)
    assert (
        result.content == "ok"
        and not backup.messages
        and attempts[0]["status"] == "success"
    )


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(),
        ConnectionError(),
        HTTPError(429),
        HTTPError(500),
        HTTPError(503),
        HTTPError(404),
        NotImplementedError(),
        HTTPError(400, "tool not supported"),
    ],
)
async def test_cross_provider_fallback(failure):
    attempts = []
    result = await ProviderManager(
        [
            Provider("alibaba", FakeModel([failure])),
            Provider("gemini", FakeModel([AIMessage(content="ok")])),
        ]
    ).invoke([], deadline(), attempts)
    assert result.content == "ok" and [a["provider"] for a in attempts] == [
        "alibaba",
        "gemini",
    ]
    assert "secret" not in str(attempts)


@pytest.mark.parametrize("status", [401, 403, 422, 400])
async def test_no_fallback_auth_and_validation(status):
    backup = FakeModel([])
    with pytest.raises(AIError):
        await ProviderManager(
            [
                Provider("alibaba", FakeModel([HTTPError(status)])),
                Provider("gemini", backup),
            ]
        ).invoke([], deadline(), [])
    assert not backup.messages


async def test_both_fail():
    with pytest.raises(AIError) as e:
        await ProviderManager(
            [
                Provider("alibaba", FakeModel([TimeoutError()])),
                Provider("gemini", FakeModel([HTTPError(503)])),
            ]
        ).invoke([], deadline(), [])
    assert e.value.detail["code"] == "AI_UNAVAILABLE" and "secret" not in str(
        e.value.detail
    )


async def test_slow_primary_leaves_fallback_budget():
    async def slow():
        await asyncio.sleep(1)

    result = await ProviderManager(
        [
            Provider("alibaba", FakeModel([slow])),
            Provider("gemini", FakeModel([AIMessage(content="ok")])),
        ]
    ).invoke([], asyncio.get_running_loop().time() + 0.05, [])
    assert result.content == "ok"


async def test_missing_credentials():
    with pytest.raises(AIError):
        await ProviderManager([]).invoke([], deadline(), [])


async def test_expired_deadline():
    with pytest.raises(AIError) as e:
        await ProviderManager([Provider("alibaba", FakeModel([]))]).invoke([], 0, [])
    assert e.value.status_code == 504


def test_real_sdk_clients_bind_without_network():
    from langchain_core.tools import StructuredTool

    from app.ai.config import Settings
    from app.ai.schemas import NoArgs, Selection

    async def ping():
        return {"ok": True}

    tool = StructuredTool.from_function(
        name="ping",
        description="Read verification value.",
        args_schema=NoArgs,
        coroutine=ping,
    )
    settings = Settings(
        alibaba_api_key="test-not-real",
        gemini_api_key="test-not-real",
        gemini_model="gemini-test-config-only",
    )
    manager = ProviderManager.configured(settings)
    assert len(manager.providers) == 2
    for provider in manager.providers:
        assert provider.model.bind_tools([tool]) is not None
        assert (
            provider.model.with_structured_output(Selection, method="function_calling")
            is not None
        )
    assert manager.providers[0].name == "alibaba:qwen-plus"


def test_legacy_key_alias_does_not_cross_providers():
    from app.ai.config import Settings

    settings = Settings(
        ai_provider="gemini",
        ai_api_key="test-not-real",
        ai_model="gemini-test-config-only",
    )
    manager = ProviderManager.configured(settings)
    assert [p.name for p in manager.providers] == ["gemini:gemini-test-config-only"]


async def test_google_sdk_http_code_is_classified():
    from google.genai.errors import ServerError

    failure = ServerError(503, {"error": {"message": "unavailable"}})
    result = await ProviderManager(
        [
            Provider("gemini", FakeModel([failure])),
            Provider("alibaba", FakeModel([AIMessage(content="ok")])),
        ]
    ).invoke([], deadline(), [])
    assert result.content == "ok"
