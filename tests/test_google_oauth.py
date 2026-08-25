import pytest

from agentguard.google_oauth import GoogleAuthorization, GoogleOAuthConfig


def test_google_oauth_config_allows_identity_scopes_only():
    config = GoogleOAuthConfig(client_id="client-id")
    assert config.scopes == ("openid", "email", "profile")
    with pytest.raises(ValueError):
        GoogleOAuthConfig(client_id="client-id", scopes=("openid", "https://www.googleapis.com/auth/drive",))
    with pytest.raises(ValueError):
        GoogleOAuthConfig(client_id="client-id", host="0.0.0.0")


def test_google_authorization_safe_metadata_excludes_token():
    authorization = GoogleAuthorization(
        access_token="secret-access-token",
        token_type="Bearer",
        expires_in=3600,
        scope="openid email profile",
        userinfo={"sub": "subject-1", "email": "agent@example.com", "email_verified": True},
    )
    safe = authorization.safe_metadata()
    assert safe["provider"] == "google"
    assert safe["subject"] == "subject-1"
    assert "access_token" not in safe
    assert "secret-access-token" not in str(safe)
