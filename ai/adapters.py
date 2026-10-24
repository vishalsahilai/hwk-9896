"""Explicit bindings to backend functions; no fallback to sample data."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .schemas import KPIContext, User
from .tools import SPECS

ReadFunction = Callable[..., Awaitable[dict]]


class ServiceAdapter:
    def __init__(
        self, reads: Mapping[str, ReadFunction], *, departments, policy, dashboard
    ):
        if set(reads) != set(SPECS):
            raise ValueError("Bind exactly the seven documented read services")
        self.reads = dict(reads)
        self._departments, self._policy, self._dashboard = (
            departments,
            policy,
            dashboard,
        )

    async def read(self, name: str, user: User, arguments: dict[str, Any]) -> dict:
        return await self.reads[name](current_user=user, **arguments)

    async def departments(self, user: User) -> list[str]:
        return await self._departments(current_user=user)

    async def policy(self, user: User) -> dict:
        return await self._policy(current_user=user)

    async def dashboard(self, user: User, context: KPIContext) -> dict:
        return await self._dashboard(current_user=user, context=context)


class OperationsAdapter:
    """Callbacks must implement durable, atomic shared reservations and log completion."""

    def __init__(self, *, reserve, complete):
        self._reserve, self._complete = reserve, complete

    async def reserve(self, user: User, feature: str, limit: int) -> str:
        return await self._reserve(current_user=user, feature=feature, limit=limit)

    async def complete(self, request_id: str, record: dict) -> None:
        await self._complete(request_id=request_id, record=record)
