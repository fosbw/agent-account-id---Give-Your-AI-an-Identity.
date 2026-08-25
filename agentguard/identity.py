from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Protocol


class IdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class IdentityRef:
    """Non-secret reference to an operator-authorized identity.

    This object intentionally cannot carry passwords, cookies, OAuth tokens, or
    recovery material. A browser provider may use an identity outside this
    process, but this package only records a reference and safe metadata.
    """

    identity_id: str
    provider: str
    subject: str
    email: str | None = None
    email_verified: bool | None = None
    authorization_basis: str = "operator_authorized"
    created_at: float = 0.0

    def safe_metadata(self) -> dict:
        return {
            "identity_id": self.identity_id,
            "provider": self.provider,
            "subject": self.subject,
            "email": self.email,
            "email_verified": self.email_verified,
            "authorization_basis": self.authorization_basis,
            "created_at": self.created_at,
        }


class IdentityAdapter(Protocol):
    provider: str

    def attach(self, metadata: Mapping[str, object]) -> IdentityRef:
        """Attach a provider-authorized identity without accepting secrets."""


class OperatorAttachedIdentityAdapter:
    """Adapter for an identity provisioned and authorized outside AgentGuard."""

    provider = "operator-attached"
    _allowed_fields = {"provider", "subject", "email", "email_verified", "authorization_basis"}
    _forbidden_names = {"password", "passwd", "cookie", "cookies", "token", "access_token", "refresh_token", "secret", "private_key"}

    def attach(self, metadata: Mapping[str, object]) -> IdentityRef:
        keys = {str(key).lower() for key in metadata}
        forbidden = sorted(keys & self._forbidden_names)
        if forbidden:
            raise IdentityError("identity metadata must not contain credentials: " + ", ".join(forbidden))
        unknown = keys - self._allowed_fields
        if unknown:
            raise IdentityError("unsupported identity metadata fields: " + ", ".join(sorted(unknown)))
        provider = str(metadata.get("provider") or self.provider).strip().lower()
        if provider != self.provider:
            raise IdentityError("operator-attached adapter cannot assert another provider")
        subject = str(metadata.get("subject") or "").strip()
        if not subject or len(subject) > 256:
            raise IdentityError("a bounded non-empty identity subject is required")
        email = metadata.get("email")
        if email is not None and (not isinstance(email, str) or len(email) > 320 or "\n" in email):
            raise IdentityError("email metadata is invalid")
        basis = str(metadata.get("authorization_basis") or "operator_authorized").strip()
        if basis not in {"operator_authorized", "provider_authorized", "test_account"}:
            raise IdentityError("authorization_basis must state an approved basis")
        return IdentityRef(
            identity_id="id-" + uuid.uuid4().hex,
            provider=provider,
            subject=subject,
            email=email,
            email_verified=metadata.get("email_verified") if isinstance(metadata.get("email_verified"), bool) else None,
            authorization_basis=basis,
            created_at=time.time(),
        )


class IdentityStore:
    """Small local metadata store; it never persists authentication material."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, identity: IdentityRef) -> None:
        path = self.root / f"{identity.identity_id}.json"
        path.write_text(json.dumps(identity.safe_metadata(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def get(self, identity_id: str) -> IdentityRef:
        if not identity_id or "/" in identity_id or "\\" in identity_id:
            raise ValueError("invalid identity id")
        path = self.root / f"{identity_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"identity not found: {identity_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return IdentityRef(**data)

    def revoke(self, identity_id: str) -> None:
        identity = self.get(identity_id)
        path = self.root / f"{identity.identity_id}.json"
        path.unlink(missing_ok=True)


class GoogleIdentityMetadataAdapter:
    """Accepts safe metadata returned by a separately authorized Google flow.

    It does not create Google accounts, import browser cookies, store OAuth
    tokens, or grant Gmail/Drive/account-administration access.
    """

    provider = "google"

    def attach(self, metadata: Mapping[str, object]) -> IdentityRef:
        clean = dict(metadata)
        clean["provider"] = self.provider
        clean.setdefault("authorization_basis", "provider_authorized")
        return _GoogleAdapterImpl().attach(clean)


class _GoogleAdapterImpl(OperatorAttachedIdentityAdapter):
    provider = "google"
    _allowed_fields = {"provider", "subject", "email", "email_verified", "authorization_basis"}

    def attach(self, metadata: Mapping[str, object]) -> IdentityRef:
        result = super().attach(metadata)
        return result
