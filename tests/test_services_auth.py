"""
Comprehensive tests for auth service.
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from app.services.auth import (
    AuthError,
    _utcnow,
    _jwt_secret,
    _jwt_algorithm,
    access_token_ttl_seconds,
    create_access_token,
    create_refresh_token,
    decode_token,
    create_user_session,
    get_session,
    list_active_sessions,
    _token_hash,
    _jwt_keyring,
    is_access_token_revoked,
    revoke_access_token,
)
from app.models.auth import TokenBlocklist, UserSession


class TestAuthUtilityFunctions:
    """Test auth utility functions."""

    def test_utcnow_returns_utc_datetime(self, app_context):
        """Test that _utcnow returns UTC datetime."""
        now = _utcnow()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None

    def test_jwt_secret_from_config(self, app_context):
        """Test getting JWT secret from config."""
        secret = _jwt_secret()
        assert secret == "test-secret-key-do-not-use-in-production"

    def test_jwt_secret_missing_raises_error(self, app):
        """Test that missing JWT secret raises AuthError."""
        with app.app_context():
            with patch.object(app, "config", {}):
                with pytest.raises(AuthError, match="JWT secret is not configured"):
                    _jwt_secret()

    def test_additional_key_with_expiry_is_ignored_when_expired(self, app):
        """Expired additional JWT keys should not be added to the keyring."""
        expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with app.app_context():
            app.config["JWT_ADDITIONAL_KEYS"] = {
                "old-key": {"secret": "old-secret", "expires_at": expired_at}
            }
            keyring = _jwt_keyring()

        assert "old-key" not in keyring
        assert keyring[app.config["JWT_ACTIVE_KID"]] == app.config["JWT_SECRET_KEY"]

    def test_jwt_algorithm_from_config(self, app_context):
        """Test getting JWT algorithm from config."""
        algo = _jwt_algorithm()
        assert algo == "HS256"

    def test_access_token_ttl_in_seconds(self, app_context):
        """Test access token TTL is returned in seconds."""
        ttl = access_token_ttl_seconds()
        assert ttl == 30 * 60  # 30 minutes * 60 seconds

    def test_token_hash_consistency(self, app_context):
        """Test that token hashing is consistent."""
        token = "test-token-12345"
        hash1 = _token_hash(token)
        hash2 = _token_hash(token)
        assert hash1 == hash2

    def test_token_hash_different_for_different_tokens(self, app_context):
        """Test that different tokens produce different hashes."""
        hash1 = _token_hash("token1")
        hash2 = _token_hash("token2")
        assert hash1 != hash2


class TestAccessTokenCreation:
    """Test access token creation and validation."""

    def test_create_access_token_success(self, app_context):
        """Test creating a valid access token."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_required_claims(self, app_context):
        """Test that access token contains all required claims."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)
        payload = jwt.decode(
            token, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )

        assert payload["sub"] == user_uuid
        assert payload["email"] == email
        assert payload["sid"] == session_uuid
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_access_token_expiry_time(self, app_context):
        """Test that access token has correct expiry time."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        before = _utcnow()
        token = create_access_token(user_uuid, email, session_uuid)
        after = _utcnow()

        payload = jwt.decode(
            token, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )

        expected_min_exp = int(before.timestamp()) + (30 * 60)
        expected_max_exp = int(after.timestamp()) + (30 * 60)

        assert expected_min_exp <= int(payload["exp"]) <= expected_max_exp

    def test_access_token_jti_is_unique(self, app_context):
        """Test that each access token has a unique JTI."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token1 = create_access_token(user_uuid, email, session_uuid)
        token2 = create_access_token(user_uuid, email, session_uuid)

        payload1 = jwt.decode(
            token1, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )
        payload2 = jwt.decode(
            token2, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )

        assert payload1["jti"] != payload2["jti"]


class TestRefreshTokenCreation:
    """Test refresh token creation and validation."""

    def test_create_refresh_token_success(self, app_context):
        """Test creating a valid refresh token."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_refresh_token(user_uuid, email, session_uuid)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_refresh_token_contains_required_claims(self, app_context):
        """Test that refresh token contains all required claims."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_refresh_token(user_uuid, email, session_uuid)
        payload = jwt.decode(
            token, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )

        assert payload["sub"] == user_uuid
        assert payload["email"] == email
        assert payload["sid"] == session_uuid
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_refresh_token_expiry_time(self, app_context):
        """Test that refresh token has correct expiry time (7 days)."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        before = _utcnow()
        token = create_refresh_token(user_uuid, email, session_uuid)
        after = _utcnow()

        payload = jwt.decode(
            token, "test-secret-key-do-not-use-in-production", algorithms=["HS256"]
        )

        expected_min_exp = int(before.timestamp()) + (7 * 24 * 60 * 60)
        expected_max_exp = int(after.timestamp()) + (7 * 24 * 60 * 60)

        assert expected_min_exp <= int(payload["exp"]) <= expected_max_exp

    def test_refresh_token_longer_ttl_than_access_token(self, app_context):
        """Test that refresh token TTL is longer than access token TTL."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        access_token = create_access_token(user_uuid, email, session_uuid)
        refresh_token = create_refresh_token(user_uuid, email, session_uuid)

        access_payload = jwt.decode(
            access_token,
            "test-secret-key-do-not-use-in-production",
            algorithms=["HS256"],
        )
        refresh_payload = jwt.decode(
            refresh_token,
            "test-secret-key-do-not-use-in-production",
            algorithms=["HS256"],
        )

        access_exp = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)
        refresh_exp = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)

        assert refresh_exp > access_exp


class TestTokenDecoding:
    """Test token decoding and validation."""

    def test_decode_valid_token(self, app_context):
        """Test decoding a valid token."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)
        payload = decode_token(token, "access")

        assert payload["sub"] == user_uuid
        assert payload["email"] == email
        assert payload["sid"] == session_uuid
        assert payload["type"] == "access"

    def test_decode_expired_token_raises_error(self, app_context):
        """Test that decoding expired token raises AuthError."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        # Create an expired token manually
        now = _utcnow()
        payload = {
            "sub": user_uuid,
            "email": email,
            "sid": session_uuid,
            "jti": "test-jti",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),  # Expired 1 hour ago
        }
        expired_token = jwt.encode(
            payload, "test-secret-key-do-not-use-in-production", algorithm="HS256"
        )

        with pytest.raises(AuthError, match="Token has expired"):
            decode_token(expired_token, "access")

    def test_decode_invalid_token_raises_error(self, app_context):
        """Test that invalid token raises AuthError."""
        with pytest.raises(AuthError, match="Invalid token"):
            decode_token("invalid-token-xyz", "access")

    def test_decode_wrong_token_type_raises_error(self, app_context):
        """Test that wrong token type raises AuthError."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        refresh_token = create_refresh_token(user_uuid, email, session_uuid)

        with pytest.raises(AuthError, match="Expected access token"):
            decode_token(refresh_token, "access")

    def test_decode_token_with_missing_claims_raises_error(self, app_context):
        """Test that token with missing claims raises AuthError."""
        payload = {
            "sub": "user-uuid",
            # Missing email, sid, jti, exp
            "type": "access",
        }
        invalid_token = jwt.encode(
            payload, "test-secret-key-do-not-use-in-production", algorithm="HS256"
        )

        with pytest.raises(AuthError, match="Token payload is invalid"):
            decode_token(invalid_token, "access")

    def test_decode_token_with_wrong_secret_raises_error(self, app_context):
        """Test that using wrong secret raises AuthError."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)

        # Try to decode with wrong secret
        with pytest.raises(AuthError, match="Invalid token"):
            with patch(
                "app.services.auth._jwt_secret",
                return_value="wrong-secret-key-for-test-0123456789",
            ):
                decode_token(token, "access")


class TestUserSessionCreation:
    """Test user session creation."""

    def test_create_user_session_success(self, app_context):
        """Test creating a user session."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session_data = create_user_session(user_uuid=user_uuid, email=email)

        assert "session_uuid" in session_data
        assert "access_token" in session_data
        assert "refresh_token" in session_data

    def test_created_session_in_database(self, app_context):
        """Test that created session is stored in database."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session_data = create_user_session(user_uuid=user_uuid, email=email)

        session = UserSession.objects(
            session_uuid=session_data["session_uuid"], user_uuid=user_uuid
        ).first()

        assert session is not None
        assert session.email == email

    def test_create_session_with_metadata(self, app_context):
        """Test creating session with metadata."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        user_agent = "Mozilla/5.0..."
        ip_address = "192.168.1.1"
        device_name = "Chrome on Windows"

        session_data = create_user_session(
            user_uuid=user_uuid,
            email=email,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )

        session = UserSession.objects(session_uuid=session_data["session_uuid"]).first()

        assert session.user_agent == user_agent
        assert session.ip_address == ip_address
        assert session.device_name == device_name

    def test_session_tokens_are_decodable(self, app_context):
        """Test that session tokens can be decoded."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session_data = create_user_session(user_uuid=user_uuid, email=email)

        access_payload = decode_token(session_data["access_token"], "access")
        refresh_payload = decode_token(session_data["refresh_token"], "refresh")

        assert access_payload["sub"] == user_uuid
        assert refresh_payload["sub"] == user_uuid


class TestGetSession:
    """Test retrieving user sessions."""

    def test_get_active_session(self, app_context):
        """Test retrieving an active session."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session_data = create_user_session(user_uuid=user_uuid, email=email)

        retrieved_session = get_session(session_data["session_uuid"], user_uuid)

        assert retrieved_session is not None
        assert retrieved_session.user_uuid == user_uuid

    def test_get_nonexistent_session_returns_none(self, app_context):
        """Test that getting nonexistent session returns None."""
        retrieved = get_session("nonexistent-session", "nonexistent-user")
        assert retrieved is None

    def test_get_inactive_session_returns_none(self, app_context):
        """Test that getting inactive session returns None."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session_data = create_user_session(user_uuid=user_uuid, email=email)

        # Mark session as inactive
        session = UserSession.objects(session_uuid=session_data["session_uuid"]).first()
        session.is_active = False
        session.save()

        retrieved = get_session(session_data["session_uuid"], user_uuid)
        assert retrieved is None


class TestListActiveSessions:
    """Test listing user's active sessions."""

    def test_list_single_active_session(self, app_context):
        """Test listing user's single active session."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        create_user_session(user_uuid=user_uuid, email=email)

        sessions = list_active_sessions(user_uuid)

        assert len(sessions) >= 1

    def test_list_multiple_active_sessions(self, app_context):
        """Test listing user's multiple active sessions."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        create_user_session(user_uuid=user_uuid, email=email)
        create_user_session(user_uuid=user_uuid, email=email)
        create_user_session(user_uuid=user_uuid, email=email)

        sessions = list_active_sessions(user_uuid)

        assert len(sessions) >= 3

    def test_list_sessions_excludes_inactive(self, app_context):
        """Test that listing sessions excludes inactive sessions."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        session1_data = create_user_session(user_uuid=user_uuid, email=email)
        session2_data = create_user_session(user_uuid=user_uuid, email=email)

        # Deactivate first session
        session1 = UserSession.objects(
            session_uuid=session1_data["session_uuid"]
        ).first()
        session1.is_active = False
        session1.save()

        sessions = list_active_sessions(user_uuid)

        session_uuids = [s.session_uuid for s in sessions]
        assert session1_data["session_uuid"] not in session_uuids
        assert session2_data["session_uuid"] in session_uuids

    def test_list_sessions_for_user_with_no_sessions(self, app_context):
        """Test listing sessions for user with no sessions."""
        sessions = list_active_sessions("nonexistent-user")
        assert len(sessions) == 0


class TestAuthEdgeCases:
    """Test auth edge cases and security scenarios."""

    def test_token_with_empty_user_uuid(self, app_context):
        """Test token with empty user UUID."""
        email = "test@example.com"
        session_uuid = "test-session"

        now = _utcnow()
        payload = {
            "sub": "",
            "email": email,
            "sid": session_uuid,
            "jti": "test-jti",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(
            payload, "test-secret-key-do-not-use-in-production", algorithm="HS256"
        )

        with pytest.raises(AuthError, match="Token payload is invalid"):
            decode_token(token, "access")

    def test_token_claims_are_immutable(self, app_context):
        """Test that modifying decoded token doesn't affect stored tokens."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)

        payload1 = decode_token(token, "access")
        payload1["sub"] = "modified"

        payload2 = decode_token(token, "access")
        assert payload2["sub"] == user_uuid

    def test_revoke_access_token_blocks_further_use(self, app_context):
        user_uuid = "test-user-uuid"
        email = "test@example.com"
        session_uuid = "test-session-uuid"

        token = create_access_token(user_uuid, email, session_uuid)
        assert is_access_token_revoked(token) is False

        revoke_access_token(token, reason="logout")

        assert is_access_token_revoked(token) is True
        with pytest.raises(AuthError, match="revoked"):
            decode_token(token, "access")

    def test_access_token_revocation_record_is_persisted(self, app_context):
        token = create_access_token("test-user-uuid", "test@example.com", "session")
        revoke_access_token(token, reason="logout")

        entry = TokenBlocklist.objects(token_type="access").first()
        assert entry is not None
        assert entry.reason == "logout"
        assert entry.expires_at is not None

    def test_session_refresh_token_hash_stored_not_token(self, app_context):
        """Test that refresh token is hashed before storage."""
        user_uuid = "test-user-uuid"
        email = "test@example.com"

        create_user_session(user_uuid=user_uuid, email=email)

        session = UserSession.objects(user_uuid=user_uuid).first()

        # refresh_token_hash should not be the actual token
        assert session.refresh_token_hash is not None
        # Should be a hash (SHA256), which is 64 hex characters
        assert len(session.refresh_token_hash) == 64
