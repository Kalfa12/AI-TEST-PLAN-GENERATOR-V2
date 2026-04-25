"""FastAPI dependency injection helpers.

All dependencies read from request.app.state, which is populated
during the lifespan in api/app.py.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from ai_testplan_generator.api.jobs import Job
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.projects import ProjectRepository
from ai_testplan_generator.events.broker import InMemoryEventBroker
from ai_testplan_generator.models import TestPlan
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.storage.base import BlobStore


def get_brain(request: Request) -> Brain:
    return cast(Brain, request.app.state.brain)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_blob_store(request: Request) -> BlobStore:
    return cast(BlobStore, request.app.state.blob_store)


def get_project_repo(request: Request) -> ProjectRepository:
    return cast(ProjectRepository, request.app.state.project_repo)


def get_event_broker(request: Request) -> InMemoryEventBroker:
    return cast(InMemoryEventBroker, request.app.state.event_broker)


def get_jobs(request: Request) -> dict[str, Job]:
    return cast(dict[str, Job], request.app.state.jobs)


def get_plans(request: Request) -> dict[str, TestPlan]:
    return cast(dict[str, TestPlan], request.app.state.plans)


def get_project_plans(request: Request) -> dict[str, list[str]]:
    return cast(dict[str, list[str]], request.app.state.project_plans)
