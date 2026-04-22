"""AI Test Plan Generator - core intelligence engine.

Provider-agnostic multi-agent brain that turns industrial specs, standards,
and requirement documents into traceable, executable test plans.
"""

from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.pipelines.autonomous import AutonomousPipeline, AutonomousResult
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.pipelines.interactive import (
    ChatReply,
    InteractivePipeline,
    InteractiveSession,
)

__all__ = [
    "AutonomousPipeline",
    "AutonomousResult",
    "Brain",
    "ChatReply",
    "InteractivePipeline",
    "InteractiveSession",
    "Settings",
    "get_settings",
]
__version__ = "0.1.0"
