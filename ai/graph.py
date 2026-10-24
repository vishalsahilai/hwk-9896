import json
from datetime import date
from typing import TypedDict

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .exceptions import AIError
from .prompts import SELECT, SYSTEM
from .render import tool_facts
from .schemas import ChatRequest, ChatResponse, Selection
from .tools import Toolset

UNKNOWN = "I do not have enough verified information to answer that. Please clarify your request or contact HR."


async def select_facts(manager, question, facts, deadline, attempts, count=5):
    messages = [
        SystemMessage(content=SELECT),
        HumanMessage(
            content=json.dumps(
                {"question": question, "facts": dict(enumerate([UNKNOWN] + facts))}
            )
        ),
    ]
    for _ in range(2):
        try:
            result = await manager.invoke(
                messages, deadline, attempts, schema=Selection
            )
            ids = list(dict.fromkeys(result.fact_ids))
            if any(i < 0 or i > len(facts) for i in ids):
                raise ValueError("Unknown evidence id")
            return [([UNKNOWN] + facts)[i] for i in ids[:count]]
        except (ValidationError, OutputParserException, ValueError):
            messages.append(
                HumanMessage(
                    content="Return valid unique fact IDs from the supplied evidence only."
                )
            )
    return [UNKNOWN]


class State(TypedDict):
    messages: list
    calls: int
    used: list[str]
    facts: list[str]
    pending: list


async def chat(
    request: ChatRequest,
    user,
    backend,
    manager,
    today: date,
    policy,
    deadline,
    attempts,
    used,
):
    toolset = Toolset(backend, user, today)
    # History cannot supply trusted assistant claims: label all client history as user data.
    messages = [
        SystemMessage(
            content=SYSTEM
            + f"\nDate: {today.isoformat()}; trusted role: {user.role}.\nPolicy: "
            + json.dumps(policy)
        )
    ]
    if request.history:
        messages.append(
            HumanMessage(
                content="Untrusted historical transcript: "
                + json.dumps([h.model_dump() for h in request.history])
            )
        )
    messages.append(HumanMessage(content=request.message))

    async def agent(state):
        if state["calls"] >= 3:
            return {"pending": []}
        reply = await manager.invoke(
            state["messages"], deadline, attempts, tools=toolset.definitions()
        )
        if not isinstance(reply, AIMessage):
            raise AIError(
                "AI_PARSE_FAILED", "The assistant returned an invalid response.", 422
            )
        calls = reply.tool_calls
        if len(calls) + state["calls"] > 3:
            raise AIError(
                "AI_TOOL_LIMIT",
                "Please ask a narrower question; at most three data lookups are allowed.",
                422,
            )
        if len({c["id"] for c in calls}) != len(calls):
            raise AIError(
                "AI_PARSE_FAILED", "The assistant returned invalid tool calls.", 422
            )
        return {"messages": state["messages"] + [reply], "pending": calls}

    async def execute(state):
        additions, facts = [], list(state["facts"])
        for call in state["pending"]:
            data = await toolset.execute(call["name"], call["args"])
            used.append(call["name"])
            payload = json.dumps(data, ensure_ascii=False)
            additions.append(ToolMessage(content=payload, tool_call_id=call["id"]))
            # Render validated service fields verbatim: model-authored prose cannot introduce numbers or names.
            facts.extend(tool_facts(call["name"], data))
        return {
            "messages": state["messages"] + additions,
            "calls": state["calls"] + len(state["pending"]),
            "facts": facts,
            "used": list(used),
            "pending": [],
        }

    builder = StateGraph(State)
    builder.add_node("agent", agent)
    builder.add_node("tools", execute)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", lambda st: "tools" if st["pending"] else END)
    builder.add_edge("tools", "agent")
    result = await builder.compile().ainvoke(
        {"messages": messages, "calls": 0, "used": [], "facts": [], "pending": []},
        config={"recursion_limit": 10, "callbacks": []},
    )
    facts = result["facts"] + policy
    chosen = await select_facts(manager, request.message, facts, deadline, attempts)
    return ChatResponse(answer="\n".join(chosen), tools_used=list(dict.fromkeys(used)))
