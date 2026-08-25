import json
from pathlib import Path

import pytest

from agentguard.identity import GoogleIdentityMetadataAdapter, IdentityError, IdentityStore, OperatorAttachedIdentityAdapter


def test_google_adapter_returns_metadata_only(tmp_path: Path):
    identity = GoogleIdentityMetadataAdapter().attach(
        {
            "subject": "google-subject-123",
            "email": "agent@example.com",
            "email_verified": True,
            "authorization_basis": "test_account",
        }
    )
    assert identity.provider == "google"
    assert identity.safe_metadata()["email"] == "agent@example.com"
    store = IdentityStore(tmp_path / "identities")
    store.save(identity)
    saved = json.loads((tmp_path / "identities" / f"{identity.identity_id}.json").read_text())
    assert set(saved) == {"identity_id", "provider", "subject", "email", "email_verified", "authorization_basis", "created_at"}
    assert not any("token" in key or "cookie" in key or "password" in key for key in saved)


def test_identity_adapter_rejects_authentication_material():
    adapter = OperatorAttachedIdentityAdapter()
    for key in ("password", "cookies", "access_token", "refresh_token", "private_key"):
        with pytest.raises(IdentityError):
            adapter.attach({"subject": "s", key: "secret-value"})


def test_identity_store_revoke(tmp_path: Path):
    identity = OperatorAttachedIdentityAdapter().attach({"subject": "s"})
    store = IdentityStore(tmp_path / "identities")
    store.save(identity)
    store.revoke(identity.identity_id)
    with pytest.raises(FileNotFoundError):
        store.get(identity.identity_id)
