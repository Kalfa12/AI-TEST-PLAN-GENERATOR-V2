"""Typed application exceptions for the HTTP API layer.

Global exception handlers in app.py convert these to structured JSON:
  {"detail": "...", "request_id": "...", "error_code": "..."}
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class AuthError(AppError):
    status_code = 401
    error_code = "AUTH_ERROR"


class ConflictError(AppError):
    status_code = 409
    error_code = "CONFLICT"


class RateLimitError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT"


class BackendUnavailable(AppError):
    status_code = 503
    error_code = "BACKEND_UNAVAILABLE"
