"""Pydantic request/response schemas for the HTTP API.

All schemas are thin wrappers over core domain models — they never
re-define fields already on the Pydantic models in ai_testplan_generator.models.
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    request_id: str
    error_code: str


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int
