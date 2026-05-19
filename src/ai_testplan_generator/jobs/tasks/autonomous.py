"""ARQ tasks: run_autonomous, delete_project_artefacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

_log = structlog.get_logger(__name__)


async def run_autonomous(
    ctx: dict[str, Any],
    *,
    project_id: str,
    goal: str,
    detail_level: str,
    max_revision_rounds: int,
    session_id: str,
) -> dict[str, Any]:
    """Run the autonomous plan-generation pipeline and persist the result."""
    from ai_testplan_generator.models import DetailLevel
    from ai_testplan_generator.pipelines.autonomous import AutonomousPipeline

    brain = ctx["brain"]
    blob_store = ctx["blob_store"]
    event_broker = ctx.get("event_broker")
    plans: dict[str, Any] = ctx.get("plans", {})
    project_plans: dict[str, list[str]] = ctx.get("project_plans", {})
    defects_index: dict[str, Any] = ctx.get("defects", {})
    job_id: str = ctx.get("job_id", "unknown")
    job_try: int = ctx.get("job_try", 1)
    max_tries: int = ctx.get("max_tries", 4)

    topic_job = f"job:{job_id}"
    topic_sess = f"session:{session_id}"

    try:
        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_start",
                "actor": "orchestrator",
                "content": "Starting autonomous plan generation.",
            })

        detail = DetailLevel(detail_level)
        pipeline = AutonomousPipeline(brain)
        result = await pipeline.run(
            project_id=project_id,
            goal=goal,
            detail_level=detail,
            max_revision_rounds=max_revision_rounds,
            session_id=session_id,
        )
        plan = result.plan
        if plan is None:
            raise RuntimeError("Pipeline completed without producing a plan.")

        plan_key = f"projects/{project_id}/plans/{plan.id}.json"
        await blob_store.put(
            plan_key, plan.model_dump_json().encode(), "application/json"
        )

        defect_report = result.state.defect_report
        if defect_report is not None:
            defects_key = f"projects/{project_id}/plans/{plan.id}.defects.json"
            await blob_store.put(
                defects_key,
                defect_report.model_dump_json().encode(),
                "application/json",
            )
            defects_index[plan.id] = defect_report

        # Update in-process index (meaningful when using FakeJobQueue in tests
        # or when the worker shares the API process's memory).
        plans[plan.id] = plan
        project_plans.setdefault(project_id, []).append(plan.id)

        out: dict[str, Any] = {
            "plan_id": plan.id,
            "n_test_cases": len(plan.test_cases),
            "n_defects": len(defect_report.defects) if defect_report else 0,
        }

        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_done",
                "actor": "orchestrator",
                "content": "Plan generation complete.",
                "metadata": out,
            })
            await event_broker.publish(topic_job, {"kind": "job_succeeded", **out})
            await event_broker.close_topic(topic_job)
            await event_broker.close_topic(topic_sess)

        _log.info("arq_autonomous_done", job_id=job_id, plan_id=plan.id)
        return out

    except Exception as exc:
        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_error",
                "actor": "orchestrator",
                "content": str(exc),
            })
            await event_broker.publish(topic_job, {"kind": "job_failed", "error": str(exc)})
            await event_broker.close_topic(topic_job)
            await event_broker.close_topic(topic_sess)

        _log.error("arq_autonomous_error", job_id=job_id, job_try=job_try, error=str(exc))

        if job_try >= max_tries:
            redis = ctx.get("redis")
            if redis is not None:
                import time

                entry = json.dumps({
                    "job_id": job_id,
                    "task_name": "run_autonomous",
                    "error": str(exc),
                    "kwargs": {
                        "project_id": project_id,
                        "goal": goal,
                        "detail_level": detail_level,
                        "max_revision_rounds": max_revision_rounds,
                        "session_id": session_id,
                    },
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                })
                await redis.zadd("jobs_deadletter", {entry: time.time()})

        raise


async def run_autonomous_interactive(
    ctx: dict[str, Any],
    *,
    project_id: str,
    goal: str,
    detail_level: str,
    max_revision_rounds: int,
    session_id: str,
) -> dict[str, Any]:
    """Run the user-gated autonomous pipeline.

    Pauses at extractor / architect / generator and waits for the resume
    endpoint to inject directives onto the Job. Only works in-process
    (FakeJobQueue) — the paused state is held in memory.
    """
    from ai_testplan_generator.models import DetailLevel
    from ai_testplan_generator.pipelines.interactive_run import (
        ResumeAborted,
        run_interactive,
    )

    brain = ctx["brain"]
    blob_store = ctx["blob_store"]
    event_broker = ctx.get("event_broker")
    plans: dict[str, Any] = ctx.get("plans", {})
    project_plans: dict[str, list[str]] = ctx.get("project_plans", {})
    defects_index: dict[str, Any] = ctx.get("defects", {})
    job_id: str = ctx.get("job_id", "unknown")
    jobs_index: dict[str, Any] = ctx.get("jobs_index", {})

    job = jobs_index.get(job_id)
    if job is None:
        raise RuntimeError(
            f"Interactive runs require an in-process Job; '{job_id}' missing"
        )

    topic_sess = f"session:{session_id}"

    try:
        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_start",
                "actor": "orchestrator",
                "content": "Starting interactive plan generation.",
            })

        result = await run_interactive(
            brain=brain,
            job=job,
            project_id=project_id,
            goal=goal,
            detail_level=DetailLevel(detail_level),
            max_revision_rounds=max_revision_rounds,
            session_id=session_id,
        )
        plan = result["plan"]

        plan_key = f"projects/{project_id}/plans/{plan.id}.json"
        await blob_store.put(
            plan_key, plan.model_dump_json().encode(), "application/json"
        )
        plans[plan.id] = plan
        project_plans.setdefault(project_id, []).append(plan.id)

        defect_report = result.get("defect_report")
        if defect_report is not None:
            defects_key = f"projects/{project_id}/plans/{plan.id}.defects.json"
            await blob_store.put(
                defects_key,
                defect_report.model_dump_json().encode(),
                "application/json",
            )
            defects_index[plan.id] = defect_report

        out: dict[str, Any] = {
            "plan_id": plan.id,
            "n_test_cases": len(plan.test_cases),
            "n_defects": len(defect_report.defects) if defect_report else 0,
        }

        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_done",
                "actor": "orchestrator",
                "content": "Interactive plan generation complete.",
                "metadata": out,
            })
            await event_broker.close_topic(topic_sess)

        _log.info("interactive_autonomous_done", job_id=job_id, plan_id=plan.id)
        return out

    except ResumeAborted:
        _log.info("interactive_aborted", job_id=job_id)
        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_error",
                "actor": "orchestrator",
                "content": "Run aborted by user.",
            })
            await event_broker.close_topic(topic_sess)
        return {"aborted": True}

    except Exception as exc:
        if event_broker is not None:
            await event_broker.publish(topic_sess, {
                "kind": "agent_error",
                "actor": "orchestrator",
                "content": str(exc),
            })
            await event_broker.close_topic(topic_sess)
        _log.error("interactive_autonomous_error", job_id=job_id, error=str(exc))
        raise


async def delete_project_artefacts(
    ctx: dict[str, Any],
    *,
    project_id: str,
) -> dict[str, Any]:
    """Cascade-delete all artefacts belonging to a project."""
    brain = ctx["brain"]
    blob_store = ctx["blob_store"]

    docs = await brain.memory.get_documents_for_project(project_id)
    deleted = 0
    for doc in docs:
        try:
            await blob_store.delete(doc.source_uri)
        except Exception:
            pass
        deleted += 1

    _log.info("arq_delete_project", project_id=project_id, deleted=deleted)
    return {"project_id": project_id, "deleted_documents": deleted}
