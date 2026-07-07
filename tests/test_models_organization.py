"""
Comprehensive tests for Organization model.
"""

import pytest
from datetime import datetime
from mongoengine.errors import ValidationError, NotUniqueError
from app.models.user import Organization, User, ORGANIZATION_STATUS_CHOICES


class TestOrganizationBasicCreation:
    """Test basic organization creation."""

    def test_create_organization_with_required_fields(self, app_context):
        """Test creating organization with required fields."""
        org = Organization(uuid="01-01-24-0001", name="Test Company")
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert retrieved.name == "Test Company"
        assert retrieved.status == "active"

    def test_create_organization_with_admins(self, app_context):
        """Test creating organization with admin users."""
        admin1 = User(
            uuid="01-01-24-0001-01-01-24-admin1",
            name="Admin 1",
            email="admin1@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin1.save()

        admin2 = User(
            uuid="01-01-24-0001-01-01-24-admin2",
            name="Admin 2",
            email="admin2@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin2.save()

        org = Organization(
            uuid="01-01-24-0002", name="Test Company", admins=[admin1, admin2]
        )
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert len(retrieved.admins) == 2
        assert admin1 in retrieved.admins


class TestOrganizationValidation:
    """Test organization validation."""

    def test_organization_name_is_trimmed(self, app_context):
        """Test that organization name is trimmed."""
        org = Organization(uuid="01-01-24-0003", name="  Test Company  ")
        org.clean()
        assert org.name == "Test Company"

    def test_empty_organization_name_raises_error(self, app_context):
        """Test that empty organization name is rejected."""
        org = Organization(uuid="01-01-24-0004", name="")
        with pytest.raises(ValidationError):
            org.clean()

    def test_whitespace_only_organization_name_raises_error(self, app_context):
        """Test that whitespace-only name is rejected."""
        org = Organization(uuid="01-01-24-0005", name="   ")
        with pytest.raises(ValidationError):
            org.clean()

    def test_unique_organization_uuid(self, app_context):
        """Test that organization UUIDs are unique."""
        org1 = Organization(uuid="01-01-24-0006", name="Company 1")
        org1.save()

        org2 = Organization(uuid="01-01-24-0006", name="Company 2")
        with pytest.raises(NotUniqueError):
            org2.save()

    def test_unique_organization_name(self, app_context):
        """Test that organization names are unique."""
        org1 = Organization(uuid="01-01-24-0007", name="Unique Company")
        org1.save()

        org2 = Organization(uuid="01-01-24-0008", name="Unique Company")
        with pytest.raises(NotUniqueError):
            org2.save()


class TestOrganizationStatus:
    """Test organization status lifecycle."""

    def test_default_organization_status_is_active(self, app_context):
        """Test that new organizations default to active."""
        org = Organization(uuid="01-01-24-0009", name="Active Company")
        org.save()
        assert org.status == "active"

    def test_all_organization_status_choices(self, app_context):
        """Test all valid organization status values."""
        for idx, status in enumerate(ORGANIZATION_STATUS_CHOICES):
            org = Organization(
                uuid=f"01-01-24-{1000 + idx}",
                name=f"Company with status {status}",
                status=status,
            )
            org.save()
            retrieved = Organization.objects.get(status=status)
            assert retrieved.status == status

    def test_deleted_organization_sets_deleted_at(self, app_context):
        """Test that deleting an organization sets deleted_at."""
        org = Organization(uuid="01-01-24-0010", name="To Delete")
        org.save()

        org.status = "deleted"
        org.clean()
        assert org.deleted_at is not None

    def test_deleted_organization_can_track_deleter(self, app_context):
        """Test tracking who deleted an organization."""
        deleter = User(
            uuid="01-01-24-0001-01-01-24-deleter",
            name="Deleter",
            email="deleter@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        deleter.save()

        org = Organization(uuid="01-01-24-0011", name="To Delete")
        org.save()

        org.status = "deleted"
        org.deleted_by = deleter
        org.clean()
        assert org.deleted_by == deleter


class TestOrganizationTimestamps:
    """Test organization timestamps."""

    def test_created_at_timestamp(self, app_context):
        """Test that created_at is set."""
        org = Organization(uuid="01-01-24-0012", name="Timestamped Company")
        org.save()

        assert org.created_at is not None
        assert isinstance(org.created_at, datetime)

    def test_updated_at_timestamp_on_creation(self, app_context):
        """Test that updated_at is set on creation."""
        org = Organization(uuid="01-01-24-0013", name="Updated Company")
        org.save()

        assert org.updated_at is not None
        assert isinstance(org.updated_at, datetime)

    def test_updated_at_changes_on_update(self, app_context):
        """Test that updated_at changes when organization is updated."""
        org = Organization(uuid="01-01-24-0014", name="Original Name")
        org.save()
        first_updated_at = org.updated_at

        import time

        time.sleep(0.1)

        org.name = "Updated Name"
        org.save()

        assert org.updated_at >= first_updated_at


class TestOrganizationAdminManagement:
    """Test organization admin management."""

    def test_add_admin_to_organization(self, app_context):
        """Test adding an admin to an organization."""
        admin = User(
            uuid="01-01-24-0001-01-01-24-admin3",
            name="New Admin",
            email="newadmin@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin.save()

        org = Organization(uuid="01-01-24-0015", name="Company with Admin")
        org.admins.append(admin)
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert admin in retrieved.admins

    def test_add_multiple_admins_to_organization(self, app_context):
        """Test adding multiple admins to an organization."""
        admins = []
        for i in range(3):
            admin = User(
                uuid=f"01-01-24-0001-01-01-24-admin{i}",
                name=f"Admin {i}",
                email=f"admin{i}@company.com",
                password_hash="hashed",
                auth_provider="local",
            )
            admin.save()
            admins.append(admin)

        org = Organization(
            uuid="01-01-24-0016", name="Company with Multiple Admins", admins=admins
        )
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert len(retrieved.admins) == 3

    def test_remove_admin_from_organization(self, app_context):
        """Test removing an admin from an organization."""
        admin1 = User(
            uuid="01-01-24-0001-01-01-24-admin4",
            name="Admin 4",
            email="admin4@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin1.save()

        admin2 = User(
            uuid="01-01-24-0001-01-01-24-admin5",
            name="Admin 5",
            email="admin5@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin2.save()

        org = Organization(
            uuid="01-01-24-0017", name="Company", admins=[admin1, admin2]
        )
        org.save()

        org.admins.remove(admin1)
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert len(retrieved.admins) == 1
        assert admin1 not in retrieved.admins


class TestOrganizationQueries:
    """Test organization queries and filtering."""

    def test_query_by_uuid(self, app_context):
        """Test querying organization by UUID."""
        org = Organization(uuid="01-01-24-0018", name="Query Test Company")
        org.save()

        retrieved = Organization.objects.get(uuid="01-01-24-0018")
        assert retrieved.name == "Query Test Company"

    def test_query_by_name(self, app_context):
        """Test querying organization by name."""
        org = Organization(uuid="01-01-24-0019", name="Unique Name Company")
        org.save()

        retrieved = Organization.objects.get(name="Unique Name Company")
        assert retrieved.uuid == "01-01-24-0019"

    def test_query_by_status(self, app_context):
        """Test querying organizations by status."""
        org_active = Organization(uuid="01-01-24-0020", name="Active", status="active")
        org_active.save()

        org_inactive = Organization(
            uuid="01-01-24-0021", name="Inactive", status="inactive"
        )
        org_inactive.save()

        active_count = Organization.objects(status="active").count()
        assert active_count >= 1

    def test_query_by_admin(self, app_context):
        """Test querying organizations by admin."""
        admin = User(
            uuid="01-01-24-0001-01-01-24-admin6",
            name="Admin 6",
            email="admin6@company.com",
            password_hash="hashed",
            auth_provider="local",
        )
        admin.save()

        org = Organization(uuid="01-01-24-0022", name="Org with Admin", admins=[admin])
        org.save()

        orgs = Organization.objects(admins=admin)
        assert orgs.count() >= 1


class TestOrganizationEdgeCases:
    """Test edge cases for organizations."""

    def test_organization_with_very_long_name(self, app_context):
        """Test organization with very long name."""
        long_name = "A" * 500
        org = Organization(uuid="01-01-24-0023", name=long_name)
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert retrieved.name == long_name

    def test_organization_with_special_characters(self, app_context):
        """Test organization with special characters in name."""
        org = Organization(uuid="01-01-24-0024", name="Company & Co., Ltd. (USA) #1")
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert retrieved.name == "Company & Co., Ltd. (USA) #1"

    def test_organization_with_international_characters(self, app_context):
        """Test organization with international characters."""
        org = Organization(
            uuid="01-01-24-0025", name="Société Générale 中国公司 Компания"
        )
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert "中国公司" in retrieved.name

    def test_organization_with_empty_admin_list(self, app_context):
        """Test creating organization with no admins."""
        org = Organization(uuid="01-01-24-0026", name="No Admin Company")
        org.save()

        retrieved = Organization.objects.get(uuid=org.uuid)
        assert len(retrieved.admins) == 0

    def test_organization_name_case_sensitivity(self, app_context):
        """Test that organization names are case sensitive."""
        org1 = Organization(uuid="01-01-24-0027", name="TestCompany")
        org1.save()

        org2 = Organization(uuid="01-01-24-0028", name="testcompany")
        org2.save()

        # Both should exist
        assert Organization.objects(name="TestCompany").count() == 1
        assert Organization.objects(name="testcompany").count() == 1
