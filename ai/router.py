from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError

from .exceptions import AIError
from .guard import AIService
from .schemas import (
    ChatRequest,
    ChatResponse,
    LeaveProposal,
    LeaveRequest,
    SummaryRequest,
    SummaryResponse,
    User,
)


class ValidatedRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                raise AIError(
                    "AI_INVALID_REQUEST",
                    "Please check the request fields and limits.",
                    422,
                ) from None

        return handler


async def authentication_required():
    # Intentionally no token parser or demo user; inject backend current_user.
    raise AIError("AUTH_REQUIRED", "Authentication is required.", 401)


async def integration_required():
    raise AIError(
        "AI_INTEGRATION_REQUIRED", "The AI backend integration is not configured."
    )


def create_router(
    current_user=authentication_required, get_service=integration_required
):
    """Mount with app.include_router(router, prefix='/api'). Dependencies may be request-scoped."""
    router = APIRouter(prefix="/ai", tags=["AI"], route_class=ValidatedRoute)

    async def trusted_user(value: Annotated[Any, Depends(current_user)]) -> User:
        # Backend auth must verify signature, expiry, active DB user and forced password changes.
        try:
            if isinstance(value, User):
                return value
            # Do not infer missing account flags from defaults on an auth object.
            fields = ("id", "role", "employee_id", "is_active", "must_change_password")
            values = {
                name: value[name] if isinstance(value, dict) else getattr(value, name)
                for name in fields
            }
            return User.model_validate(values)
        except (ValidationError, KeyError, AttributeError):
            raise AIError(
                "AUTH_REQUIRED", "A valid authenticated account is required.", 401
            ) from None

    @router.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(
        request: ChatRequest,
        user: Annotated[User, Depends(trusted_user)],
        service: Annotated[AIService, Depends(get_service)],
    ):
        return await service.run("chat", request, user)

    @router.post("/summary", response_model=SummaryResponse)
    async def summary_endpoint(
        request: SummaryRequest,
        user: Annotated[User, Depends(trusted_user)],
        service: Annotated[AIService, Depends(get_service)],
    ):
        return await service.run("summary", request, user)

    @router.post("/smart-leave", response_model=LeaveProposal)
    async def leave_endpoint(
        request: LeaveRequest,
        user: Annotated[User, Depends(trusted_user)],
        service: Annotated[AIService, Depends(get_service)],
    ):
        return await service.run("smart_leave", request, user)

    return router


router = create_router()
