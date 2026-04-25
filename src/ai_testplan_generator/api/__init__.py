"""HTTP API package for the AI Test Plan Generator.

Entry point:
    uvicorn ai_testplan_generator.api.app:create_app --factory --port 8000
"""

from ai_testplan_generator.api.app import create_app

__all__ = ["create_app"]
