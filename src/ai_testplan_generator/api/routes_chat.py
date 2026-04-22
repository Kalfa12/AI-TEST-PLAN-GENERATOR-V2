"""Routes: interactive chat / copilot.

POST /chat  — send a message and get an assistant reply
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_testplan_generator.api.deps import get_brain
from ai_testplan_generator.pipelines.brain import Brain
from ai_testplan_generator.pipelines.interactive import InteractivePipeline

_log = structlog.get_logger(__name__)

router = APIRouter(tags=["chat"])

# Module-level pipeline instance so sessions persist across requests.
_pipeline: InteractivePipeline | None = None


def _get_pipeline(brain: Brain = Depends(get_brain)) -> InteractivePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = InteractivePipeline(brain)
    return _pipeline


# ---- request / response models ---------------------------------------------

class ChatRequest(BaseModel):
    project_id: str | None = None
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    pending_action: str | None = None


# ---- endpoint --------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    pipeline: InteractivePipeline = Depends(_get_pipeline),
) -> ChatResponse:
    """Send a message to the copilot and receive an assistant reply.

    - Pass `session_id` to continue an existing conversation.
    - Pass `project_id` to scope retrieval to a specific project's corpus.
    """
    try:
        session = pipeline.session(project_id=body.project_id, session_id=body.session_id)
        reply = await session.ask(body.message)
        return ChatResponse(
            session_id=session.session_id,
            assistant_message=reply.assistant_message,
            pending_action=reply.pending_action,
        )
    except Exception as exc:
        _log.error("api_chat_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
