import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from .config import Settings
from .exceptions import AIError, unavailable


@dataclass(frozen=True)
class Provider:
    name: str
    model: Any


class ProviderManager:
    def __init__(self, providers: list[Provider]):
        self.providers = providers

    @classmethod
    def configured(cls, settings: Settings):
        providers = []
        key = settings.alibaba_api_key.get_secret_value() or (
            settings.ai_api_key.get_secret_value()
            if settings.ai_provider == "alibaba"
            else ""
        )
        if key:
            from langchain_openai import ChatOpenAI

            for name in dict.fromkeys(
                [
                    (settings.ai_model if settings.ai_provider == "alibaba" else "")
                    or settings.alibaba_tool_model,
                    settings.alibaba_fallback_model,
                ]
            ):
                if name and "character" not in name.casefold():
                    providers.append(
                        Provider(
                            "alibaba:" + name,
                            ChatOpenAI(
                                model=name,
                                api_key=key,
                                base_url=settings.alibaba_base_url,
                                temperature=0,
                                max_retries=0,
                                timeout=settings.ai_timeout_seconds,
                                max_tokens=1800,
                            ),
                        )
                    )
        key = settings.gemini_api_key.get_secret_value() or (
            settings.ai_api_key.get_secret_value()
            if settings.ai_provider == "gemini"
            else ""
        )
        if key and (
            settings.gemini_model
            or (settings.ai_model if settings.ai_provider == "gemini" else "")
        ):
            from langchain_google_genai import ChatGoogleGenerativeAI

            name = settings.gemini_model or settings.ai_model
            providers.append(
                Provider(
                    "gemini:" + name,
                    ChatGoogleGenerativeAI(
                        model=name,
                        api_key=key,
                        temperature=0,
                        max_retries=0,
                        timeout=settings.ai_timeout_seconds,
                        max_output_tokens=1800,
                    ),
                )
            )
        if settings.ai_provider == "gemini":
            providers.sort(key=lambda p: not p.name.startswith("gemini:"))
        return cls(providers)

    async def invoke(
        self,
        messages,
        deadline: float,
        attempts: list[dict],
        *,
        tools=None,
        schema: type[BaseModel] | None = None,
    ):
        if not self.providers:
            raise unavailable()
        for index, provider in enumerate(self.providers):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise AIError(
                    "AI_TIMEOUT", "The assistant took too long. Please try again.", 504
                )
            # Leave time for cross-provider fallback. Entire workflow has an outer deadline too.
            budget = (
                remaining
                if index == len(self.providers) - 1
                else remaining / (len(self.providers) - index)
            )
            record = {"provider": provider.name, "status": "started"}
            attempts.append(record)
            try:
                model = provider.model
                if tools:
                    model = model.bind_tools(tools)
                if schema:
                    model = model.with_structured_output(
                        schema, method="function_calling"
                    )
                async with asyncio.timeout(budget):
                    result = await model.ainvoke(messages, config={"callbacks": []})
                if schema:
                    result = schema.model_validate(result)
                record["status"] = "success"
                return result
            except (ValidationError, OutputParserException, AIError):
                record["status"] = "validation_or_authorization"
                raise
            except Exception as exc:  # noqa: BLE001 -- classify SDK failures without exposing provider text
                status = getattr(exc, "status_code", None)
                if status is None:
                    status = getattr(
                        getattr(exc, "response", None), "status_code", None
                    )
                if status is None:
                    code = getattr(exc, "code", None)
                    if isinstance(code, int):
                        status = code  # google-genai errors expose HTTP status as code.
                record["status"] = "failed"
                record["http_status"] = status
                # Provider credentials are not user authorization. Fail closed; no retry for 401/403.
                if status in {401, 403}:
                    raise unavailable() from None
                retryable = isinstance(
                    exc, (TimeoutError, ConnectionError, NotImplementedError)
                ) or status in {404, 408, 429, 500, 502, 503, 504}
                if status == 400:
                    text = str(exc).casefold()
                    retryable = any(
                        word in text
                        for word in ("tool", "function", "model", "not supported")
                    )
                retryable = retryable or type(exc).__name__ in {
                    "APIConnectionError",
                    "APITimeoutError",
                    "ServiceUnavailable",
                    "ResourceExhausted",
                    "NotFound",
                    "ConnectError",
                    "ConnectTimeout",
                    "ReadTimeout",
                    "RemoteProtocolError",
                }
                if not retryable:
                    raise unavailable() from None
        raise unavailable()
