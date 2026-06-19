"""Tests for UserRepository (M12)."""

from __future__ import annotations

import pytest

from ai_testplan_generator.domain.users import UserRepository
from ai_testplan_generator.api.security.password import hash_password
from ai_testplan_generator.api.security.api_key import generate_api_key, build_full_key


@pytest.fixture
async def repo(tmp_path):  # type: ignore[no-untyped-def]
    r = await UserRepository.create(db_path=str(tmp_path / "test.db"))
    yield r
    await r.close()


async def test_create_and_get_user(repo: UserRepository) -> None:
    user = await repo.create_user(
        email="alice@example.com",
        display_name="Alice",
        password_hash=hash_password("secret"),
    )
    assert user.id.startswith("usr_")
    assert user.is_active

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"

    by_email = await repo.get_by_email("alice@example.com")
    assert by_email is not None
    assert by_email.id == user.id


async def test_admin_flag_persists(repo: UserRepository) -> None:
    user = await repo.create_user(
        email="admin@example.com",
        display_name="Admin",
        is_admin=True,
    )

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.is_admin


async def test_get_nonexistent_user(repo: UserRepository) -> None:
    assert await repo.get_by_id("usr_doesnotexist") is None
    assert await repo.get_by_email("nobody@example.com") is None


async def test_disable_user(repo: UserRepository) -> None:
    user = await repo.create_user(email="bob@example.com", display_name="Bob")
    assert user.is_active

    ok = await repo.disable_user(user.id)
    assert ok

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert not fetched.is_active

    # Double-disable returns False.
    ok2 = await repo.disable_user(user.id)
    assert not ok2


async def test_api_key_create_and_revoke(repo: UserRepository) -> None:
    user = await repo.create_user(email="carol@example.com", display_name="Carol")
    raw_material, key_hash = generate_api_key()

    key = await repo.create_api_key(
        user_id=user.id, name="my-key", key_hash=key_hash
    )
    assert key.id.startswith("key_")
    assert not key.is_revoked

    full_key = build_full_key(key.id, raw_material)
    assert full_key == f"{key.id}.{raw_material}"

    # Lookup by ID.
    fetched = await repo.get_api_key_by_id(key.id)
    assert fetched is not None
    assert fetched.user_id == user.id

    # List keys.
    keys = await repo.get_api_keys(user.id)
    assert len(keys) == 1

    # Revoke.
    ok = await repo.revoke_api_key(key.id)
    assert ok

    revoked = await repo.get_api_key_by_id(key.id)
    assert revoked is not None
    assert revoked.is_revoked

    # Double-revoke returns False.
    assert not await repo.revoke_api_key(key.id)


async def test_touch_api_key(repo: UserRepository) -> None:
    user = await repo.create_user(email="dave@example.com", display_name="Dave")
    _, key_hash = generate_api_key()
    key = await repo.create_api_key(user_id=user.id, name="k", key_hash=key_hash)

    assert key.last_used_at is None
    await repo.touch_api_key(key.id)

    updated = await repo.get_api_key_by_id(key.id)
    assert updated is not None
    assert updated.last_used_at is not None


async def test_multiple_users_isolated(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = await UserRepository.create(db_path=str(tmp_path / "iso.db"))
    u1 = await repo.create_user(email="u1@x.com", display_name="U1")
    u2 = await repo.create_user(email="u2@x.com", display_name="U2")

    _, h1 = generate_api_key()
    _, h2 = generate_api_key()
    await repo.create_api_key(user_id=u1.id, name="k1", key_hash=h1)
    await repo.create_api_key(user_id=u2.id, name="k2", key_hash=h2)

    assert len(await repo.get_api_keys(u1.id)) == 1
    assert len(await repo.get_api_keys(u2.id)) == 1
    await repo.close()
