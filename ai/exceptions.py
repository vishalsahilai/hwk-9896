from fastapi import HTTPException


class AIError(HTTPException):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(status, {"code": code, "message": message})


def unavailable() -> AIError:
    return AIError(
        "AI_UNAVAILABLE",
        "The assistant is unavailable. Please try again or use the normal form.",
    )
