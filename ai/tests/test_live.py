"""Opt-in, billable smoke tests. No .env files are discovered or loaded."""

import asyncio
import os

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool

from app.ai.config import Settings
from app.ai.providers import ProviderManager
from app.ai.schemas import NoArgs, Selection


@pytest.mark.skipif(
    os.environ.get("AI_RUN_LIVE") != "1",
    reason="Live requests are opt-in (AI_RUN_LIVE=1); credentials and configured models required.",
)
async def test_live_both_providers_tool_calling_and_structured_output():
    settings = Settings()
    manager = ProviderManager.configured(settings)
    assert any(p.name.startswith("alibaba:") for p in manager.providers)
    assert any(p.name.startswith("gemini:") for p in manager.providers)

    async def ping():
        return {"value": 1}

    tool = StructuredTool.from_function(
        name="ping",
        description="Read the verification value.",
        args_schema=NoArgs,
        coroutine=ping,
    )
    for provider in (
        next(p for p in manager.providers if p.name.startswith("alibaba:")),
        next(p for p in manager.providers if p.name.startswith("gemini:")),
    ):
        one = ProviderManager([provider])
        attempts = []
        reply = await one.invoke(
            [
                SystemMessage(content="You must call ping to get the value."),
                HumanMessage(content="Use ping now."),
            ],
            asyncio.get_running_loop().time() + 15,
            attempts,
            tools=[tool],
        )
        assert isinstance(reply, AIMessage) and any(
            c["name"] == "ping" for c in reply.tool_calls
        )
        result = await one.invoke(
            [HumanMessage(content="Return fact_ids containing only integer 1.")],
            asyncio.get_running_loop().time() + 15,
            attempts,
            schema=Selection,
        )
        assert result.fact_ids == [1]
