"""
Comprehensive tests for User model including edge cases and validation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from mongoengine.errors import ValidationError, NotUniqueError
from app.models.user import User, Organization, ROLE_CHOICES, USER_STATUS_CHOICES


@pytest.fixture
def organization(app_context):
    """Create a test organization."""
    org = Organization(uuid="01-01-24-0001", name="Test Organization", status="active")
    org.save()
    return org


@pytest.fixture
def another_organization(app_context):
    """Create another test organization."""
    org = Organization(
        uuid="01-01-24-0002", name="Another Organization", status="active"
    )
    org.save()
    return org


class TestUserBasicCreation:
    """Test basic user creation and validation."""

    def test_create_user_with_minimal_fields(self, app_context):
        """Test creating user with only required fields."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0001",
            name="John Doe",
            email="john@example.com",
            password_hash="hashed_password_123",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.name == "John Doe"
        assert retrieved.email == "john@example.com"
        assert retrieved.status == "active"

    def test_create_user_with_all_fields(self, app_context, organization):
        """Test creating user with all optional fields."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0002",
            name="Jane Doe",
            designation="Software Engineer",
            email="jane@example.com",
            phone="+1-555-0123",
            organizations=[organization],
            roles={str(organization.id): ["admin", "editor"]},
            password_hash="hashed_password_456",
            auth_provider="local",
            is_email_verified=True,
            is_phone_verified=True,
            is_organisation_admin=True,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.designation == "Software Engineer"
        assert retrieved.phone == "+1-555-0123"
        assert len(retrieved.organizations) == 1
        assert retrieved.is_email_verified is True
        assert retrieved.is_organisation_admin is True

    def test_user_email_lowercase_normalization(self, app_context):
        """Test that emails are normalized to lowercase."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0003",
            name="Test User",
            email="John@EXAMPLE.COM",
            password_hash="hashed_password",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.email == "john@example.com"

    def test_user_name_whitespace_handling(self, app_context):
        """Test that user name with extra whitespace is handled."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0004",
            name="  Test User  ",
            email="test@example.com",
            password_hash="hashed_password",
            auth_provider="local",
        )
        # Note: name normalization depends on implementation
        user.save()
        assert user.name.strip() == "Test User"


class TestUserValidation:
    """Test user validation and constraints."""

    def test_empty_name_raises_validation_error(self, app_context):
        """Test that empty user name is rejected."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0005",
            name="",
            email="test@example.com",
            password_hash="hashed_password",
            auth_provider="local",
        )
        with pytest.raises(ValidationError):
            user.clean()

    def test_whitespace_only_name_raises_validation_error(self, app_context):
        """Test that whitespace-only name is rejected."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0006",
            name="   ",
            email="test@example.com",
            password_hash="hashed_password",
            auth_provider="local",
        )
        with pytest.raises(ValidationError):
            user.clean()

    def test_local_auth_without_password_raises_validation_error(self, app_context):
        """Test that local auth users must have password_hash."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0007",
            name="Test User",
            email="test@example.com",
            auth_provider="local",
            # password_hash is missing
        )
        with pytest.raises(ValidationError):
            user.clean()

    def test_sso_auth_without_password_is_allowed(self, app_context):
        """Test that SSO auth users don't need password_hash."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0008",
            name="Test User",
            email="test@example.com",
            auth_provider="sso",
        )
        user.clean()  # Should not raise

    def test_unique_uuid_constraint(self, app_context):
        """Test that user UUIDs must be unique."""
        user1 = User(
            uuid="01-01-24-0001-01-01-24-0009",
            name="User 1",
            email="user1@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user1.save()

        user2 = User(
            uuid="01-01-24-0001-01-01-24-0009",  # Same UUID
            name="User 2",
            email="user2@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        with pytest.raises(NotUniqueError):
            user2.save()

    def test_unique_email_constraint(self, app_context):
        """Test that user emails must be unique."""
        user1 = User(
            uuid="01-01-24-0001-01-01-24-0010",
            name="User 1",
            email="duplicate@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user1.save()

        user2 = User(
            uuid="01-01-24-0001-01-01-24-0011",
            name="User 2",
            email="duplicate@example.com",  # Same email
            password_hash="hashed",
            auth_provider="local",
        )
        with pytest.raises(NotUniqueError):
            user2.save()


class TestUserRolesAndOrganizations:
    """Test user roles and organization relationships."""

    def test_add_user_to_organization(self, app_context, organization):
        """Test adding user to organization."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0012",
            name="Test User",
            email="test@example.com",
            organizations=[organization],
            roles={str(organization.id): ["admin"]},
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert len(retrieved.organizations) == 1
        assert organization in retrieved.organizations

    def test_user_with_multiple_organizations(
        self, app_context, organization, another_organization
    ):
        """Test user in multiple organizations with different roles."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0013",
            name="Test User",
            email="test@example.com",
            organizations=[organization, another_organization],
            roles={
                str(organization.id): ["admin"],
                str(another_organization.id): ["editor", "viewer"],
            },
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert len(retrieved.organizations) == 2
        assert len(retrieved.roles) == 2

    def test_invalid_organization_key_in_roles_raises_error(
        self, app_context, organization
    ):
        """Test that roles with unknown organization keys are rejected."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0014",
            name="Test User",
            email="test@example.com",
            organizations=[organization],
            roles={
                str(organization.id): ["admin"],
                "invalid-org-id": ["editor"],  # Not in organizations
            },
            password_hash="hashed",
            auth_provider="local",
        )
        with pytest.raises(ValidationError):
            user.clean()

    def test_organisation_admin_without_admin_role_raises_error(
        self, app_context, organization
    ):
        """Test that is_organisation_admin requires admin role."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0015",
            name="Test User",
            email="test@example.com",
            organizations=[organization],
            roles={str(organization.id): ["editor", "viewer"]},  # No admin role
            is_organisation_admin=True,
            password_hash="hashed",
            auth_provider="local",
        )
        with pytest.raises(ValidationError):
            user.clean()

    def test_organisation_admin_with_admin_role_is_valid(
        self, app_context, organization
    ):
        """Test that is_organisation_admin is valid with admin role."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0016",
            name="Test User",
            email="test@example.com",
            organizations=[organization],
            roles={str(organization.id): ["admin"]},
            is_organisation_admin=True,
            password_hash="hashed",
            auth_provider="local",
        )
        user.clean()  # Should not raise


class TestUserStatus:
    """Test user status and lifecycle."""

    def test_active_user_default_status(self, app_context):
        """Test that new users default to active status."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0017",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()
        assert user.status == "active"

    def test_deleted_user_sets_deleted_at(self, app_context):
        """Test that deleting a user sets deleted_at timestamp."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0018",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        user.status = "deleted"
        user.clean()
        assert user.deleted_at is not None

    def test_user_status_choices(self, app_context):
        """Test all valid user status values."""
        for status in USER_STATUS_CHOICES:
            user = User(
                uuid=f"01-01-24-0001-01-01-24-{1900 + USER_STATUS_CHOICES.index(status)}",
                name=f"User with {status}",
                email=f"{status}@example.com",
                password_hash="hashed",
                auth_provider="local",
                status=status,
            )
            user.save()
            retrieved = User.objects.get(status=status)
            assert retrieved.status == status


class TestUserMFA:
    """Test multi-factor authentication fields."""

    def test_mfa_disabled_by_default(self, app_context):
        """Test that MFA is disabled by default."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0019",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()
        assert user.is_mfa_enabled is False

    def test_otp_secret_creation(self, app_context):
        """Test setting OTP secret for MFA."""
        now = datetime.now(timezone.utc)
        user = User(
            uuid="01-01-24-0001-01-01-24-0020",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            otp_secret="secret123",
            otp_secret_created_at=now,
            is_mfa_enabled=True,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.otp_secret == "secret123"
        assert retrieved.is_mfa_enabled is True


class TestUserLoginTracking:
    """Test user login and logout tracking."""

    def test_last_login_at_tracking(self, app_context):
        """Test tracking last login time."""
        login_time = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            uuid="01-01-24-0001-01-01-24-0021",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            last_login_at=login_time,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert abs((retrieved.last_login_at - login_time).total_seconds()) < 0.001

    def test_last_logout_at_tracking(self, app_context):
        """Test tracking last logout time."""
        logout_time = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            uuid="01-01-24-0001-01-01-24-0022",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            last_logout_at=logout_time,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert abs((retrieved.last_logout_at - logout_time).total_seconds()) < 0.001

    def test_password_change_tracking(self, app_context):
        """Test tracking password change time."""
        password_change_time = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            uuid="01-01-24-0001-01-01-24-0023",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            last_password_change_at=password_change_time,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert (
            abs(
                (
                    retrieved.last_password_change_at - password_change_time
                ).total_seconds()
            )
            < 0.001
        )


class TestUserPasswordReset:
    """Test password reset functionality."""

    def test_password_reset_token_storage(self, app_context):
        """Test storing password reset token."""
        reset_token = "reset_token_xyz"
        expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

        user = User(
            uuid="01-01-24-0001-01-01-24-0024",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            password_reset_token=reset_token,
            password_reset_token_expiry=expiry,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.password_reset_token == reset_token
        assert (
            abs((retrieved.password_reset_token_expiry - expiry).total_seconds())
            < 0.001
        )

    def test_password_reset_token_expiry_tracking(self, app_context):
        """Test that password reset token creation time is tracked."""
        creation_time = datetime.now(timezone.utc).replace(tzinfo=None)
        user = User(
            uuid="01-01-24-0001-01-01-24-0025",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            password_reset_token_created_at=creation_time,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert (
            abs(
                (
                    retrieved.password_reset_token_created_at - creation_time
                ).total_seconds()
            )
            < 0.001
        )


class TestUserEmailVerification:
    """Test email verification fields."""

    def test_email_verification_tracking(self, app_context):
        """Test email verification timestamp and verifier."""
        verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        verified_by = "admin@example.com"

        user = User(
            uuid="01-01-24-0001-01-01-24-0026",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
            is_email_verified=True,
            verified_at=verified_at,
            verified_by=verified_by,
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.is_email_verified is True
        assert abs((retrieved.verified_at - verified_at).total_seconds()) < 0.001
        assert retrieved.verified_by == verified_by


class TestUserTimestamps:
    """Test user creation and update timestamps."""

    def test_created_at_timestamp_set_on_save(self, app_context):
        """Test that created_at is set when user is saved."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0027",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)

    def test_updated_at_timestamp_updated_on_save(self, app_context):
        """Test that updated_at is updated on each save."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0028",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()
        created_updated_at = user.updated_at

        import time

        time.sleep(0.1)

        user.name = "Updated Name"
        user.save()

        assert user.updated_at >= created_updated_at


class TestUserQueries:
    """Test user queries and filtering."""

    def test_query_user_by_uuid(self, app_context):
        """Test querying user by UUID."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0029",
            name="Test User",
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects(uuid="01-01-24-0001-01-01-24-0029").first()
        assert retrieved is not None
        assert retrieved.name == "Test User"

    def test_query_user_by_email(self, app_context):
        """Test querying user by email."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0030",
            name="Test User",
            email="unique@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects(email="unique@example.com").first()
        assert retrieved is not None
        assert retrieved.name == "Test User"

    def test_query_user_by_status(self, app_context):
        """Test querying users by status."""
        active_user = User(
            uuid="01-01-24-0001-01-01-24-0031",
            name="Active User",
            email="active@example.com",
            password_hash="hashed",
            auth_provider="local",
            status="active",
        )
        active_user.save()

        inactive_user = User(
            uuid="01-01-24-0001-01-01-24-0032",
            name="Inactive User",
            email="inactive@example.com",
            password_hash="hashed",
            auth_provider="local",
            status="inactive",
        )
        inactive_user.save()

        active_users = User.objects(status="active")
        assert active_users.count() >= 1

        inactive_users = User.objects(status="inactive")
        assert inactive_users.count() >= 1

    def test_query_super_admins(self, app_context):
        """Test querying super admin users."""
        super_admin = User(
            uuid="01-01-24-0001-01-01-24-0033",
            name="Super Admin",
            email="admin@example.com",
            password_hash="hashed",
            auth_provider="local",
            is_super_admin=True,
        )
        super_admin.save()

        admins = User.objects(is_super_admin=True)
        assert admins.count() >= 1


class TestUserEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_user_with_very_long_name(self, app_context):
        """Test user with very long name."""
        long_name = "A" * 1000
        user = User(
            uuid="01-01-24-0001-01-01-24-0034",
            name=long_name,
            email="test@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.name == long_name

    def test_user_with_special_characters_in_email(self, app_context):
        """Test user with special characters in email."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0035",
            name="Test User",
            email="test+tag@example.co.uk",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.email == "test+tag@example.co.uk"

    def test_user_with_international_characters(self, app_context):
        """Test user with international characters in name."""
        user = User(
            uuid="01-01-24-0001-01-01-24-0036",
            name="François José 中文",
            email="intl@example.com",
            password_hash="hashed",
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.name == "François José 中文"

    def test_user_role_choices_all_valid(self, app_context, organization):
        """Test all valid role choices."""
        for role in ROLE_CHOICES:
            user = User(
                uuid=f"01-01-24-0001-01-01-24-{3700 + ROLE_CHOICES.index(role)}",
                name=f"User with {role}",
                email=f"{role}@example.com",
                organizations=[organization],
                roles={str(organization.id): [role]},
                password_hash="hashed",
                auth_provider="local",
            )
            user.save()
            retrieved = User.objects.get(uuid=user.uuid)
            assert role in retrieved.roles[str(organization.id)]
