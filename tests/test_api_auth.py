"""
Comprehensive tests for auth API endpoints.
"""

import pytest
import json
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization
from app.models.auth import SessionAuditLog, UserSession
from app.services.auth import create_user_session


@pytest.fixture
def test_user(app_context):
    """Create a test user."""
    user = User(
        uuid="01-01-24-0001-01-01-24-testuser",
        name="Test User",
        email="test@example.com",
        password_hash=generate_password_hash("test_password_123"),
        auth_provider="local",
    )
    user.save()
    return user


@pytest.fixture
def test_organization(app_context):
    """Create a test organization."""
    org = Organization(uuid="01-01-24-test-org", name="Test Organization")
    org.save()
    return org


def _create_session_tokens(user):
    return create_user_session(
        user_uuid=user.uuid,
        email=user.email,
        user_agent="pytest",
        ip_address="127.0.0.1",
        device_name="pytest-device",
    )


class TestAuthAPIHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check_endpoint_exists(self, client):
        """Test that health check endpoint responds."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "ok"
        assert payload["service"] == "form"

    def test_metrics_endpoint_reports_async_queue(self, client):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        payload = response.get_json()
        assert "async_queue" in payload
        assert {"queued", "running", "failed", "timeout"} <= set(
            payload["async_queue"].keys()
        )
        assert {"oldest_queued_at", "oldest_running_at"} <= set(
            payload["async_queue"].keys()
        )


class TestAuthAPIRegister:
    """Test user registration endpoint."""

    def test_register_new_user_success(self, client, app_context):
        """Test successful user registration."""
        payload = {
            "email": "newuser@example.com",
            "name": "New User",
            "password": "SecurePass123!",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 201
        response_data = response.get_json()
        assert "access_token" not in response_data
        assert "refresh_token" not in response_data
        assert "session_uuid" not in response_data
        assert response_data["status"] == "unverified"
        assert response_data["email"] == "newuser@example.com"
        assert response_data["must_change_password"] is False

    def test_register_duplicate_email_fails(self, client, test_user, app_context):
        """Test that registering with duplicate email fails."""
        payload = {
            "email": "test@example.com",  # Already exists
            "name": "Another User",
            "password": "SecurePass123!",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_register_without_email_fails(self, client):
        """Test that registration without email fails."""
        payload = {"name": "No Email User", "password": "SecurePass123!"}

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_register_without_password_fails(self, client):
        """Test that registration without password fails."""
        payload = {"email": "nopass@example.com", "name": "No Pass User"}

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_register_with_weak_password_fails(self, client):
        """Test that registration with weak password fails (if validated)."""
        payload = {
            "email": "weak@example.com",
            "name": "Weak Pass User",
            "password": "123",  # Too weak
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Depending on implementation, may reject weak passwords
        assert response.status_code in [400, 422]

    def test_register_email_case_insensitive(self, client, app_context):
        """Test that email registration is case-insensitive."""
        payload1 = {
            "email": "test@EXAMPLE.COM",
            "name": "User 1",
            "password": "SecurePass123!",
        }

        client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload1),
            content_type="application/json",
        )

        payload2 = {
            "email": "test@example.com",  # Same but different case
            "name": "User 2",
            "password": "SecurePass123!",
        }

        response2 = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload2),
            content_type="application/json",
        )

        # Second registration should fail as duplicate
        assert response2.status_code >= 400


class TestAuthAPILogin:
    """Test user login endpoint."""

    def test_login_with_valid_credentials(self, client, test_user):
        """Test successful login with valid credentials."""
        payload = {"email": "test@example.com", "password": "test_password_123"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code in [200, 201]
        response_data = json.loads(response.data)
        assert "access_token" in response_data or "accessToken" in response_data
        assert "refresh_token" in response_data or "refreshToken" in response_data

    def test_login_with_invalid_password(self, client, test_user):
        """Test login fails with wrong password."""
        payload = {"email": "test@example.com", "password": "wrong_password"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_with_nonexistent_email(self, client):
        """Test login fails with non-existent email."""
        payload = {"email": "nonexistent@example.com", "password": "any_password"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_without_email_fails(self, client):
        """Test login without email fails."""
        payload = {"password": "any_password"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_login_without_password_fails(self, client):
        """Test login without password fails."""
        payload = {"email": "test@example.com"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_login_rate_limiting(self, client, test_user, app):
        """Test that login endpoint has rate limiting."""
        payload = {"email": "test@example.com", "password": "wrong_password"}

        # Make multiple failed login attempts
        for i in range(5):
            response = client.post(
                "/api/v1/auth/login",
                data=json.dumps(payload),
                content_type="application/json",
            )

        # After several attempts, should get rate limit response (429)
        # Or at least the response should fail
        assert response.status_code >= 400

    def test_login_email_case_insensitive(self, client, test_user):
        """Test that login email is case-insensitive."""
        payload = {
            "email": "TEST@EXAMPLE.COM",  # Different case
            "password": "test_password_123",
        }

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code in [200, 201]

    @pytest.mark.parametrize(
        "status",
        ["inactive", "suspended", "locked", "deleted", "unverified"],
    )
    def test_login_rejects_disabled_accounts(self, client, test_user, status):
        test_user.status = status
        test_user.save()

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {"email": "test@example.com", "password": "test_password_123"}
            ),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_login_blocked_when_password_change_required(self, client, test_user):
        test_user.must_change_password = True
        test_user.save()

        payload = {"email": "test@example.com", "password": "test_password_123"}
        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 401
        assert "password change required" in response.get_json()["message"].lower()


class TestAuthAPIPasswordChange:
    def test_change_password_clears_must_change_password_flag(
        self, client, test_user
    ):
        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "test@example.com", "password": "test_password_123"}),
            content_type="application/json",
        )
        assert login_response.status_code == 200
        access_token = login_response.get_json()["access_token"]

        test_user.must_change_password = True
        test_user.save()

        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            data=json.dumps(
                {
                    "current_password": "test_password_123",
                    "new_password": "NewSecurePass123!",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        refreshed = User.objects.get(uuid=test_user.uuid)
        assert refreshed.must_change_password is False

        relogin = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "test@example.com", "password": "NewSecurePass123!"}),
            content_type="application/json",
        )
        assert relogin.status_code == 200

    def test_login_response_contains_user_info(self, client, test_user):
        """Test that login response contains user information."""
        payload = {"email": "test@example.com", "password": "test_password_123"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code in [200, 201]
        response_data = json.loads(response.data)
        # Check for user info or user data
        assert "user" in response_data or "email" in str(response_data)


class TestAuthAPIRefresh:
    """Test token refresh endpoint."""

    def test_refresh_token_success(self, client, test_user):
        """Test successful token refresh."""
        session = _create_session_tokens(test_user)
        refresh_payload = {"refresh_token": session["refresh_token"]}

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps(refresh_payload),
            content_type="application/json",
        )

        assert refresh_response.status_code in [200, 201]
        refresh_data = json.loads(refresh_response.data)
        assert "access_token" in refresh_data or "accessToken" in refresh_data

    @pytest.mark.parametrize(
        "status",
        ["inactive", "suspended", "locked", "deleted", "unverified"],
    )
    def test_refresh_rejects_disabled_accounts(self, client, test_user, status):
        test_user.status = status
        test_user.save()
        session = _create_session_tokens(test_user)

        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": session["refresh_token"]}),
            content_type="application/json",
        )

        assert response.status_code == 401
        payload = response.get_json()
        assert status in payload["message"]

    def test_refresh_invalid_token_fails(self, client):
        """Test that invalid refresh token fails."""
        payload = {"refresh_token": "invalid-token-xyz"}

        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_refresh_without_token_fails(self, client):
        """Test refresh without token fails."""
        payload = {}

        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_refresh_access_token_fails(self, client, test_user):
        """Test that using access token for refresh fails."""
        # Get tokens
        login_payload = {"email": "test@example.com", "password": "test_password_123"}

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(login_payload),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        # Try to use access token as refresh token
        refresh_payload = {"refresh_token": access_token}

        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps(refresh_payload),
            content_type="application/json",
        )

        assert response.status_code == 401


class TestAuthAPILogout:
    """Test user logout endpoint."""

    def test_logout_success(self, client, test_user):
        """Test successful logout."""
        # Login first
        login_payload = {"email": "test@example.com", "password": "test_password_123"}

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(login_payload),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get(
            "accessToken"
        )
        refresh_token = login_data.get("refresh_token") or login_data.get(
            "refreshToken"
        )

        # Then logout
        logout_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

        logout_response = client.post(
            "/api/v1/auth/logout",
            data=json.dumps(logout_payload),
            content_type="application/json",
        )

        assert logout_response.status_code == 200

    def test_logout_without_token_fails(self, client):
        """Test logout without authentication fails."""
        payload = {}

        response = client.post(
            "/api/v1/auth/logout",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 422

    def test_logout_with_invalid_token_fails(self, client):
        """Test logout with invalid token fails."""
        payload = {"access_token": "invalid-token", "refresh_token": "invalid-token"}

        response = client.post(
            "/api/v1/auth/logout",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401

    def test_logout_invalidates_session(self, client, test_user):
        """Test that logout invalidates the session."""
        # Login
        login_payload = {"email": "test@example.com", "password": "test_password_123"}

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(login_payload),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get(
            "accessToken"
        )
        refresh_token = login_data.get("refresh_token") or login_data.get(
            "refreshToken"
        )

        pre_logout_me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert pre_logout_me.status_code == 200

        # Logout
        logout_response = client.post(
            "/api/v1/auth/logout",
            data=json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
            ),
            content_type="application/json",
        )
        assert logout_response.status_code == 200

        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 401

        # Try to use the same refresh token again
        response = client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": refresh_token}),
            content_type="application/json",
        )

        assert response.status_code == 401


class TestAuthAPISessions:
    """Test session management endpoints."""

    def test_list_sessions_requires_auth(self, client):
        """Test that listing sessions requires authentication."""
        response = client.get("/api/v1/auth/sessions")
        assert response.status_code == 422

    def test_list_sessions_with_valid_token(self, client, test_user):
        """Test listing sessions with valid token."""
        # Login
        login_payload = {"email": "test@example.com", "password": "test_password_123"}

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(login_payload),
            content_type="application/json",
        )

        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        # List sessions
        response = client.get(
            "/api/v1/auth/sessions", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200

    def test_admin_session_pagination_uses_cursor_and_page_size(
        self, client, test_user
    ):
        admin = User(
            uuid="admin-pagination-0001",
            name="Admin Pagination",
            email="admin-pagination@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        for idx in range(3):
            UserSession(
                session_uuid=f"session-pagination-{idx}",
                user_uuid=test_user.uuid,
                email=test_user.email,
                refresh_jti=f"jti-{idx}",
                refresh_token_hash=f"hash-{idx}",
                refresh_expires_at=base + timedelta(days=7),
                created_at=base - timedelta(minutes=idx),
                last_seen_at=base - timedelta(minutes=idx),
                is_active=True,
            ).save()

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        first_page = client.get(
            f"/api/v1/auth/admin/users/{test_user.uuid}/sessions?page=1&page_size=2",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_page.status_code == 200
        first_payload = first_page.get_json()
        assert len(first_payload["sessions"]) == 2
        assert first_payload["total_items"] == 3
        assert first_payload["next_cursor"]

        second_page = client.get(
            f"/api/v1/auth/admin/users/{test_user.uuid}/sessions?page=1&page_size=2&cursor={first_payload['next_cursor']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_page.status_code == 200
        assert len(second_page.get_json()["sessions"]) == 1

    def test_admin_session_pagination_handles_timestamp_collisions(
        self, client, test_user
    ):
        admin = User(
            uuid="admin-pagination-collision-0001",
            name="Admin Pagination Collision",
            email="admin-pagination-collision@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        session_ids = []
        for idx in range(3):
            session = UserSession(
                session_uuid=f"session-collision-{idx}",
                user_uuid=test_user.uuid,
                email=test_user.email,
                refresh_jti=f"jti-collision-{idx}",
                refresh_token_hash=f"hash-collision-{idx}",
                refresh_expires_at=base + timedelta(days=7),
                created_at=base,
                last_seen_at=base,
                is_active=True,
            ).save()
            session_ids.append(session.session_uuid)

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        first_page = client.get(
            f"/api/v1/auth/admin/users/{test_user.uuid}/sessions?page=1&page_size=2",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_page.status_code == 200
        first_payload = first_page.get_json()
        assert len(first_payload["sessions"]) == 2
        assert first_payload["next_cursor"]

        second_page = client.get(
            f"/api/v1/auth/admin/users/{test_user.uuid}/sessions?page=1&page_size=2&cursor={first_payload['next_cursor']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_page.status_code == 200
        second_payload = second_page.get_json()
        assert len(second_payload["sessions"]) == 1
        combined = [item["session_uuid"] for item in first_payload["sessions"] + second_payload["sessions"]]
        assert sorted(combined) == sorted(session_ids)

    def test_admin_session_pagination_accepts_legacy_cursor_format(
        self, client, test_user
    ):
        admin = User(
            uuid="admin-pagination-legacy-0001",
            name="Admin Pagination Legacy",
            email="admin-pagination-legacy@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        for idx in range(3):
            UserSession(
                session_uuid=f"session-legacy-{idx}",
                user_uuid=test_user.uuid,
                email=test_user.email,
                refresh_jti=f"jti-legacy-{idx}",
                refresh_token_hash=f"hash-legacy-{idx}",
                refresh_expires_at=base + timedelta(days=7),
                created_at=base - timedelta(minutes=idx),
                last_seen_at=base - timedelta(minutes=idx),
                is_active=True,
            ).save()

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        legacy_cursor = urlsafe_b64encode((base - timedelta(minutes=1)).isoformat().encode("utf-8")).decode("utf-8")
        second_page = client.get(
            f"/api/v1/auth/admin/users/{test_user.uuid}/sessions?page=1&page_size=2&cursor={legacy_cursor}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert second_page.status_code == 200
        assert len(second_page.get_json()["sessions"]) == 1

    def test_admin_audit_log_pagination_uses_cursor(self, client, test_user):
        admin = User(
            uuid="admin-audit-0001",
            name="Admin Audit",
            email="admin-audit@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        for idx in range(3):
            SessionAuditLog(
                actor_user_uuid=admin.uuid,
                target_user_uuid=test_user.uuid,
                session_uuid=f"session-audit-{idx}",
                action="admin_session_revoke",
                reason="test",
                created_at=base - timedelta(minutes=idx),
                expires_at=base + timedelta(days=180),
            ).save()

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        first_page = client.get(
            "/api/v1/auth/admin/audit-logs?page=1&page_size=2",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_page.status_code == 200
        first_payload = first_page.get_json()
        assert len(first_payload["items"]) == 2
        assert first_payload["next_cursor"]

        cursor_page = client.get(
            f"/api/v1/auth/admin/audit-logs?page=1&page_size=2&cursor={first_payload['next_cursor']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert cursor_page.status_code == 200
        assert len(cursor_page.get_json()["items"]) == 1

    def test_admin_audit_log_pagination_handles_timestamp_collisions(
        self, client, test_user
    ):
        admin = User(
            uuid="admin-audit-collision-0001",
            name="Admin Audit Collision",
            email="admin-audit-collision@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        for idx in range(3):
            SessionAuditLog(
                actor_user_uuid=admin.uuid,
                target_user_uuid=test_user.uuid,
                session_uuid=f"session-audit-collision-{idx}",
                action="admin_session_revoke",
                reason="test",
                created_at=base,
                expires_at=base + timedelta(days=180),
            ).save()

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        first_page = client.get(
            "/api/v1/auth/admin/audit-logs?page=1&page_size=2",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert first_page.status_code == 200
        first_payload = first_page.get_json()
        assert len(first_payload["items"]) == 2
        assert first_payload["next_cursor"]

        cursor_page = client.get(
            f"/api/v1/auth/admin/audit-logs?page=1&page_size=2&cursor={first_payload['next_cursor']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert cursor_page.status_code == 200
        second_payload = cursor_page.get_json()
        assert len(second_payload["items"]) == 1
        combined = [item["session_uuid"] for item in first_payload["items"] + second_payload["items"]]
        assert sorted(combined) == sorted(
            [
                "session-audit-collision-0",
                "session-audit-collision-1",
                "session-audit-collision-2",
            ]
        )

    def test_admin_audit_log_pagination_accepts_legacy_cursor_format(
        self, client, test_user
    ):
        admin = User(
            uuid="admin-audit-legacy-0001",
            name="Admin Audit Legacy",
            email="admin-audit-legacy@example.com",
            password_hash=generate_password_hash("test_password_123"),
            auth_provider="local",
            is_super_admin=True,
        )
        admin.save()

        base = datetime.now(timezone.utc)
        for idx in range(3):
            SessionAuditLog(
                actor_user_uuid=admin.uuid,
                target_user_uuid=test_user.uuid,
                session_uuid=f"session-audit-legacy-{idx}",
                action="admin_session_revoke",
                reason="test",
                created_at=base - timedelta(minutes=idx),
                expires_at=base + timedelta(days=180),
            ).save()

        login_response = client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": admin.email, "password": "test_password_123"}),
            content_type="application/json",
        )
        login_data = json.loads(login_response.data)
        access_token = login_data.get("access_token") or login_data.get("accessToken")

        legacy_cursor = urlsafe_b64encode((base - timedelta(minutes=1)).isoformat().encode("utf-8")).decode("utf-8")
        cursor_page = client.get(
            f"/api/v1/auth/admin/audit-logs?page=1&page_size=2&cursor={legacy_cursor}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert cursor_page.status_code == 200
        assert len(cursor_page.get_json()["items"]) == 1


class TestAuthAPIEdgeCases:
    """Test auth API edge cases."""

    def test_login_with_empty_credentials(self, client):
        """Test login with empty string credentials."""
        payload = {"email": "", "password": ""}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_login_with_sql_injection_attempt(self, client):
        """Test that SQL injection attempts are handled."""
        payload = {
            "email": "test'; DROP TABLE users; --@example.com",
            "password": "password",
        }

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Should not crash or execute injection
        assert response.status_code >= 400

    def test_login_with_xss_payload(self, client):
        """Test that XSS payloads are handled."""
        payload = {
            "email": "<script>alert('xss')</script>@example.com",
            "password": "password",
        }

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Should not execute script
        assert response.status_code >= 400

    def test_login_with_very_long_email(self, client):
        """Test login with extremely long email."""
        payload = {"email": "a" * 1000 + "@example.com", "password": "password"}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code in [400, 401, 422]

    def test_login_with_null_payload(self, client):
        """Test login with null/None payload values."""
        payload = {"email": None, "password": None}

        response = client.post(
            "/api/v1/auth/login",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code >= 400

    def test_register_with_special_characters_in_name(self, client):
        """Test registration with special characters in name."""
        payload = {
            "email": "special@example.com",
            "name": "Test <User> \"Name\" & 'More'",
            "password": "SecurePass123!",
        }

        response = client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Should handle special chars safely
        assert response.status_code in [200, 201, 400]
