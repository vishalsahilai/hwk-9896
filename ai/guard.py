import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .dashboard_summary import summarize
from .exceptions import AIError
from .graph import chat
from .policy import Policy
from .smart_leave import propose


class AIService:
    def __init__(self, backend, operations, manager, settings, clock=None):
        self.backend, self.operations, self.manager, self.settings = (
            backend,
            operations,
            manager,
            settings,
        )
        self.clock = clock or (
            lambda: datetime.now(ZoneInfo(settings.ai_timezone)).date()
        )

    async def current_policy(self, user):
        data = await self.backend.policy(user)
        required = {
            "office_start",
            "grace_minutes",
            "half_day_hours",
            "weekend_days",
            "leave_quotas",
        }
        if not required.issubset(data):
            raise AIError(
                "AI_INTEGRATION_REQUIRED", "Current company policy is unavailable."
            )
        return Policy.model_validate(data)

    async def run(self, feature, request, user):
        if not user.is_active:
            raise AIError("ACCOUNT_INACTIVE", "Your account is inactive.", 403)
        if user.must_change_password:
            raise AIError(
                "PASSWORD_CHANGE_REQUIRED",
                "Please change your password before continuing.",
                403,
            )
        roles = {
            "chat": {"admin", "hr", "employee"},
            "summary": {"admin", "hr"},
            "smart_leave": {"hr", "employee"},
        }
        if user.role not in roles[feature]:
            raise AIError("AI_FORBIDDEN", "You cannot use this AI feature.", 403)
        started = time.monotonic()
        attempts = []
        used = []
        reservation = None
        success = False
        code = None
        overall_deadline = (
            asyncio.get_running_loop().time() + self.settings.ai_timeout_seconds
        )
        cleanup_budget = min(0.25, self.settings.ai_timeout_seconds * 0.1)
        deadline = overall_deadline - cleanup_budget
        try:
            async with asyncio.timeout_at(deadline):
                reservation = await self.operations.reserve(
                    user, feature, self.settings.ai_rate_limit_per_hour
                )
                if feature == "chat":
                    policy = (await self.current_policy(user)).facts()
                    result = await chat(
                        request,
                        user,
                        self.backend,
                        self.manager,
                        self.clock(),
                        policy,
                        deadline,
                        attempts,
                        used,
                    )
                elif feature == "summary":
                    result = await summarize(
                        request, user, self.backend, self.manager, deadline, attempts
                    )
                else:
                    policy = await self.current_policy(user)
                    result = await propose(
                        request, self.manager, self.clock(), deadline, attempts
                    )
                    if result.leave_type not in policy.leave_quotas:
                        raise AIError(
                            "AI_PARSE_FAILED",
                            "This leave type is unavailable. Please use the normal form.",
                            422,
                        )
                success = True
                return result
        except TimeoutError:
            code = "AI_TIMEOUT"
            raise AIError(
                code,
                "The assistant took too long. Please try again or use the normal form.",
                504,
            ) from None
        except AIError as exc:
            code = exc.detail["code"]
            raise
        except Exception:  # noqa: BLE001 -- sanitize errors at the external boundary
            code = "AI_UNAVAILABLE"
            raise AIError(
                code,
                "The assistant is temporarily unavailable. Please use the normal form.",
            ) from None
        finally:
            if reservation:
                # No user text, model output or exception strings: operational metadata only.
                # A small part of the overall request deadline is reserved for persistence.
                try:
                    async with asyncio.timeout_at(overall_deadline):
                        await self.operations.complete(
                            reservation,
                            {
                                "user_id": user.id,
                                "feature": feature,
                                "prompt": "[redacted]",
                                "tools_called": used,
                                "response": "[redacted]" if success else code,
                                "latency_ms": int((time.monotonic() - started) * 1000),
                                "success": success,
                                "attempts": attempts,
                            },
                        )
                except Exception:  # noqa: BLE001 -- sanitize errors at the external boundary
                    # A reserved row must already exist; adapter marks stale reservations as failed.
                    import logging

                    logging.getLogger(__name__).error(
                        "AI log completion failed; reserved record requires reconciliation"
                    )
