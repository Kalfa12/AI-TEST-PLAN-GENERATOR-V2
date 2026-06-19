"""M10: Projects and members endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestProjectCRUD:
    async def test_create_project(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/projects",
            json={"name": "Pump Controller Tests", "description": "ISO 4413 qualification"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Pump Controller Tests"
        assert body["id"].startswith("proj_")
        assert body["owner_id"] == "usr_test000001"

        members = await client.get(f"/projects/{body['id']}/members")
        assert members.status_code == 200
        assert any(
            m["user_id"] == "usr_test000001" and m["role"] == "owner"
            for m in members.json()
        )

    async def test_list_projects_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["items"], list)

    async def test_get_project_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/projects/proj_nonexistent")
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "NOT_FOUND"

    async def test_create_then_get(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "Test Project"}
        )
        project_id = create_resp.json()["id"]
        get_resp = await client.get(f"/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == project_id

    async def test_update_project(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "Old Name"}
        )
        project_id = create_resp.json()["id"]
        patch_resp = await client.patch(
            f"/projects/{project_id}", json={"name": "New Name"}
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "New Name"

    async def test_archive_project(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "To Archive"}
        )
        project_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/projects/{project_id}")
        assert del_resp.status_code == 204

    async def test_archive_project_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete("/projects/proj_nonexistent")
        assert resp.status_code == 404


class TestProjectMembers:
    async def test_add_and_list_members(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "Member Test Project"}
        )
        project_id = create_resp.json()["id"]

        add_resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": "usr_alice", "role": "editor"},
        )
        assert add_resp.status_code == 201
        member = add_resp.json()
        assert member["user_id"] == "usr_alice"
        assert member["role"] == "editor"

        list_resp = await client.get(f"/projects/{project_id}/members")
        assert list_resp.status_code == 200
        members = list_resp.json()
        assert any(m["user_id"] == "usr_alice" for m in members)

    async def test_remove_member(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "Remove Member Project"}
        )
        project_id = create_resp.json()["id"]
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": "usr_bob", "role": "viewer"},
        )
        del_resp = await client.delete(
            f"/projects/{project_id}/members/usr_bob"
        )
        assert del_resp.status_code == 204

    async def test_remove_member_not_found(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/projects", json={"name": "No Members Project"}
        )
        project_id = create_resp.json()["id"]
        resp = await client.delete(
            f"/projects/{project_id}/members/usr_nonexistent"
        )
        assert resp.status_code == 404
