"""
Comprehensive integration tests combining multiple components.
"""

import pytest
from werkzeug.security import generate_password_hash
from app.models.user import User, Organization


class TestUserOrganizationIntegration:
    """Test user and organization integration."""

    def test_user_in_multiple_organizations(self, app_context):
        """Test user being member of multiple organizations."""
        org1 = Organization(uuid="01-01-24-0001", name="Org 1")
        org2 = Organization(uuid="01-01-24-0002", name="Org 2")
        org1.save()
        org2.save()

        user = User(
            uuid="01-01-24-0001-01-01-24-multiorg",
            name="Multi Org User",
            email="multiorg@example.com",
            organizations=[org1, org2],
            roles={str(org1.id): ["admin"], str(org2.id): ["editor"]},
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert len(retrieved.organizations) == 2
        assert len(retrieved.roles) == 2

    def test_organization_admin_is_user(self, app_context):
        """Test that organization admins are valid users."""
        admin = User(
            uuid="01-01-24-0001-01-01-24-admin",
            name="Admin User",
            email="admin@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        admin.save()

        org = Organization(uuid="01-01-24-0003", name="Org with Admin", admins=[admin])
        org.save()

        retrieved_org = Organization.objects.get(uuid=org.uuid)
        assert admin in retrieved_org.admins

    def test_user_deletion_affects_organization_admins(self, app_context):
        """Test deleting admin user from organization."""
        admin = User(
            uuid="01-01-24-0001-01-01-24-admin2",
            name="Admin User",
            email="admin2@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        admin.save()

        org = Organization(
            uuid="01-01-24-0004", name="Org for Admin Removal", admins=[admin]
        )
        org.save()

        # Mark user as deleted
        admin.status = "deleted"
        admin.save()

        # Organization should still reference the deleted user
        retrieved_org = Organization.objects.get(uuid=org.uuid)
        assert admin in retrieved_org.admins


class TestDataConsistency:
    """Test data consistency across operations."""

    def test_user_email_consistency_after_update(self, app_context):
        """Test that user email remains consistent after updates."""
        user = User(
            uuid="01-01-24-0001-01-01-24-consistency",
            name="Original Name",
            email="original@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        # Update name but not email
        user.name = "Updated Name"
        user.save()

        # Query by original email
        retrieved = User.objects.get(email="original@example.com")
        assert retrieved.name == "Updated Name"

    def test_user_uniqueness_constraints_after_operations(self, app_context):
        """Test that uniqueness is maintained through operations."""
        from mongoengine.errors import NotUniqueError

        user1 = User(
            uuid="01-01-24-0001-01-01-24-unique1",
            name="User 1",
            email="unique@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user1.save()

        # Try to create duplicate after first is saved
        user2 = User(
            uuid="01-01-24-0001-01-01-24-unique2",
            name="User 2",
            email="unique@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )

        with pytest.raises(NotUniqueError):
            user2.save()

    def test_organization_name_consistency(self, app_context):
        """Test organization name remains consistent."""
        org = Organization(uuid="01-01-24-0005", name="Original Name")
        org.save()

        # Add admin
        admin = User(
            uuid="01-01-24-0001-01-01-24-admin3",
            name="Admin",
            email="admin3@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        admin.save()

        org.admins.append(admin)
        org.save()

        # Name should still be original
        retrieved = Organization.objects.get(uuid=org.uuid)
        assert retrieved.name == "Original Name"


class TestBulkOperations:
    """Test bulk operations on users and organizations."""

    def test_create_multiple_users_with_same_organization(self, app_context):
        """Test creating multiple users in same organization."""
        org = Organization(uuid="01-01-24-0006", name="Bulk User Org")
        org.save()

        users = []
        for i in range(5):
            user = User(
                uuid=f"01-01-24-0001-01-01-24-bulk{i}",
                name=f"Bulk User {i}",
                email=f"bulk{i}@example.com",
                organizations=[org],
                roles={str(org.id): ["editor"]},
                password_hash=generate_password_hash("password"),
                auth_provider="local",
            )
            user.save()
            users.append(user)

        org_users = User.objects(organizations=org)
        assert org_users.count() >= 5

    def test_bulk_status_updates(self, app_context):
        """Test updating status for multiple users."""
        users = []
        for i in range(3):
            user = User(
                uuid=f"01-01-24-0001-01-01-24-statupd{i}",
                name=f"Status Update User {i}",
                email=f"statupd{i}@example.com",
                password_hash=generate_password_hash("password"),
                auth_provider="local",
                status="active",
            )
            user.save()
            users.append(user)

        # Deactivate all
        User.objects(email__in=[u.email for u in users]).update(set__status="inactive")

        # Verify
        for user in users:
            retrieved = User.objects.get(uuid=user.uuid)
            assert retrieved.status == "inactive"


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_save_invalid_user_does_not_corrupt_db(self, app_context):
        """Test that saving invalid data doesn't corrupt database."""
        from mongoengine.errors import ValidationError

        # Try to save invalid user
        invalid_user = User(
            uuid="01-01-24-0001-01-01-24-invalid",
            name="",  # Invalid: empty name
            email="invalid@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )

        with pytest.raises(ValidationError):
            invalid_user.save()

        # Database should still be accessible
        # Try to save valid user
        valid_user = User(
            uuid="01-01-24-0001-01-01-24-valid",
            name="Valid User",
            email="valid@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        valid_user.save()

        retrieved = User.objects.get(uuid=valid_user.uuid)
        assert retrieved.name == "Valid User"

    def test_query_nonexistent_data_returns_empty(self, app_context):
        """Test that querying nonexistent data returns empty, not error."""
        users = User.objects(email="nonexistent@example.com")
        assert users.count() == 0
        assert list(users) == []


class TestPerformance:
    """Test performance-related scenarios."""

    def test_create_large_number_of_users(self, app_context):
        """Test creating large number of users."""
        for i in range(50):
            user = User(
                uuid=f"01-01-24-0001-01-01-24-perf{i}",
                name=f"Performance Test User {i}",
                email=f"perf{i}@example.com",
                password_hash=generate_password_hash("password"),
                auth_provider="local",
            )
            user.save()

        # Verify count
        count = User.objects.count()
        assert count >= 50

    def test_query_with_index(self, app_context):
        """Test that indexed queries are efficient."""
        # Create user
        user = User(
            uuid="01-01-24-0001-01-01-24-indexed",
            name="Indexed User",
            email="indexed@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        # Query by UUID (should be indexed)
        retrieved = User.objects(uuid="01-01-24-0001-01-01-24-indexed").first()
        assert retrieved is not None

        # Query by email (should be indexed)
        retrieved = User.objects(email="indexed@example.com").first()
        assert retrieved is not None

    def test_large_list_field(self, app_context):
        """Test user with large number of organizations."""
        orgs = []
        for i in range(10):
            org = Organization(uuid=f"01-01-24-large{i:02d}", name=f"Large Org {i}")
            org.save()
            orgs.append(org)

        roles = {str(org.id): ["viewer"] for org in orgs}

        user = User(
            uuid="01-01-24-0001-01-01-24-largeorg",
            name="Many Org User",
            email="largeorg@example.com",
            organizations=orgs,
            roles=roles,
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert len(retrieved.organizations) == 10


class TestDataMigration:
    """Test data migration and transformation scenarios."""

    def test_user_status_transition_sequence(self, app_context):
        """Test valid user status transitions."""
        user = User(
            uuid="01-01-24-0001-01-01-24-transition",
            name="Status Transition User",
            email="transition@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
            status="active",
        )
        user.save()
        assert user.status == "active"

        # Suspend user
        user.status = "suspended"
        user.save()
        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.status == "suspended"

        # Activate again
        user.status = "active"
        user.save()
        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.status == "active"

    def test_role_assignment_and_removal(self, app_context):
        """Test assigning and removing roles."""
        org1 = Organization(uuid="01-01-24-0007", name="Org 1")
        org2 = Organization(uuid="01-01-24-0008", name="Org 2")
        org1.save()
        org2.save()

        user = User(
            uuid="01-01-24-0001-01-01-24-roleassign",
            name="Role Assignment User",
            email="roleassign@example.com",
            organizations=[org1],
            roles={str(org1.id): ["editor"]},
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        # Add organization and role
        user.organizations.append(org2)
        user.roles[str(org2.id)] = ["admin"]
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert len(retrieved.organizations) == 2
        assert len(retrieved.roles) == 2


class TestAuditFields:
    """Test audit and tracking fields."""

    def test_created_updated_timestamps_sequence(self, app_context):
        """Test created_at and updated_at timestamp sequence."""
        import time

        user = User(
            uuid="01-01-24-0001-01-01-24-audit",
            name="Audit User",
            email="audit@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        created_at = user.created_at
        updated_at = user.updated_at

        assert created_at <= updated_at

        time.sleep(0.1)

        user.name = "Modified Audit User"
        user.save()

        assert user.updated_at > updated_at

    def test_deleted_at_tracking(self, app_context):
        """Test tracking when user is deleted."""
        user = User(
            uuid="01-01-24-0001-01-01-24-deltrack",
            name="Deletion Tracking User",
            email="deltrack@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        assert user.deleted_at is None

        user.status = "deleted"
        user.clean()
        assert user.deleted_at is not None

    def test_last_login_tracking(self, app_context):
        """Test tracking last login timestamp."""
        from datetime import datetime

        user = User(
            uuid="01-01-24-0001-01-01-24-login",
            name="Login Tracking User",
            email="login@example.com",
            password_hash=generate_password_hash("password"),
            auth_provider="local",
        )
        user.save()

        assert user.last_login_at is None

        user.last_login_at = datetime.utcnow()
        user.save()

        retrieved = User.objects.get(uuid=user.uuid)
        assert retrieved.last_login_at is not None
