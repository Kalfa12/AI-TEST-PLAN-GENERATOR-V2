"""Phase 8 planning/resource endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_resource_crud_api(client: AsyncClient) -> None:
    create_project = await client.post("/projects", json={"name": "Planning Project"})
    assert create_project.status_code == 201
    project_id = create_project.json()["id"]

    create_resource = await client.post(
        f"/projects/{project_id}/resources",
        json={
            "name": "Validation bench",
            "service": "System test lab",
            "role": "Technician",
            "availability_pct": 80,
        },
    )
    assert create_resource.status_code == 201
    resource = create_resource.json()
    assert resource["project_id"] == project_id
    assert resource["name"] == "Validation bench"

    listed = await client.get(f"/projects/{project_id}/resources")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = await client.patch(
        f"/projects/{project_id}/resources/{resource['id']}",
        json={"availability_pct": 60, "role": "Lead technician"},
    )
    assert patched.status_code == 200
    assert patched.json()["availability_pct"] == 60
    assert patched.json()["role"] == "Lead technician"

    deleted = await client.delete(f"/projects/{project_id}/resources/{resource['id']}")
    assert deleted.status_code == 204

    listed_again = await client.get(f"/projects/{project_id}/resources")
    assert listed_again.status_code == 200
    assert listed_again.json()["total"] == 0


async def test_schedule_missing_plan_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/projects/proj-missing/plans/plan-missing/schedule")
    assert resp.status_code == 404
