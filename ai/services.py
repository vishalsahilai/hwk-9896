"""Backend-owned contracts. No production data, authentication or DB implementation."""

from typing import Any, Protocol

from .schemas import KPIContext, User


class Backend(Protocol):
    async def read(self, name: str, user: User, arguments: dict[str, Any]) -> dict:
        """Dispatch only the seven named read services. Enforce role + own scope independently."""
        ...

    async def departments(self, user: User) -> list[str]: ...
    async def policy(self, user: User) -> dict:
        """Return policy-safe current settings + quotas, not raw settings or secrets."""
        ...

    async def dashboard(self, user: User, context: KPIContext) -> dict:
        """Authoritative dashboard using the same filters as REST; never trust client KPIs."""
        ...


class Operations(Protocol):
    async def reserve(self, user: User, feature: str, limit: int) -> str:
        """Atomically reserve an attempt across workers and ALL features for rolling hour.
        Raise AIError(429) when exceeded. Persist before inference; returns request id.
        """
        ...

    async def complete(self, request_id: str, record: dict) -> None:
        """Durably update operational ai_logs record; no HR business writes."""
        ...
