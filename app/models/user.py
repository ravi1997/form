from app.extensions import db
from datetime import datetime
from mongoengine.errors import ValidationError

ROLE_CHOICES = (
    "admin",
    "editor",
    "viewer",
    "reviewer",
    "approver",
    "submitter",
)

USER_STATUS_CHOICES = (
    "active",
    "inactive",
    "deleted",
    "suspended",
    "locked",
)

ORGANIZATION_STATUS_CHOICES = (
    "active",
    "inactive",
    "deleted",
)


class Organization(db.Document):
    uuid = db.StringField(required=True, unique=True)  # DD-MM-YY-XXXX
    name = db.StringField(required=True, unique=True)

    admins = db.ListField(db.ReferenceField("User"))

    created_at = db.DateTimeField(default=datetime.utcnow)
    updated_at = db.DateTimeField(default=datetime.utcnow)
    status = db.StringField(choices=ORGANIZATION_STATUS_CHOICES, default="active")
    deleted_at = db.DateTimeField()
    deleted_by = db.ReferenceField("User")

    meta = {
        "collection": "organizations",
        "indexes": ["uuid", "name", "status"],
    }

    def clean(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError("Organization name cannot be empty")

        if self.status == "deleted" and not self.deleted_at:
            self.deleted_at = datetime.utcnow()

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


class User(db.Document):
    # DD-MM-YY-OOOO-DD-MM-YY-XXXX
    uuid = db.StringField(required=True, unique=True)

    name = db.StringField(required=True)

    designation = db.StringField()
    email = db.StringField(required=True, unique=True)
    phone = db.StringField()

    # store organization IDs (recommended instead of embedding full objects)
    organizations = db.ListField(db.ReferenceField("Organization"))

    # Map<Organization, Vector<String>>
    # stored as: { "org_id": ["role1", "role2"] }
    roles = db.MapField(db.ListField(db.StringField(choices=ROLE_CHOICES)))

    created_at = db.DateTimeField(default=datetime.utcnow)
    updated_at = db.DateTimeField(default=datetime.utcnow)

    verified_at = db.DateTimeField()
    verified_by = db.StringField()

    deleted_at = db.DateTimeField()
    deleted_by = db.StringField()

    last_login_at = db.DateTimeField()
    last_logout_at = db.DateTimeField()
    last_password_change_at = db.DateTimeField()

    status = db.StringField(choices=USER_STATUS_CHOICES, default="active")

    auth_provider = db.StringField(choices=["local", "sso"], default="local")

    password_hash = db.StringField()

    password_reset_token = db.StringField()
    password_reset_token_expiry = db.DateTimeField()
    password_reset_token_created_at = db.DateTimeField()

    otp_secret = db.StringField()
    otp_secret_created_at = db.DateTimeField()

    is_email_verified = db.BooleanField(default=False)
    is_phone_verified = db.BooleanField(default=False)
    is_organisation_admin = db.BooleanField(default=False)
    is_super_admin = db.BooleanField(default=False)
    is_mfa_enabled = db.BooleanField(default=False)

    meta = {
        "collection": "users",
        "indexes": ["uuid", "email", "status", "is_super_admin"],
    }

    def clean(self):
        if self.email:
            self.email = self.email.strip().lower()

        if not self.name.strip():
            raise ValidationError("User name cannot be empty")

        if self.auth_provider == "local" and not self.password_hash:
            raise ValidationError("password_hash is required for local auth users")

        if self.status == "deleted" and not self.deleted_at:
            self.deleted_at = datetime.utcnow()

        if self.roles and self.organizations:
            organization_keys = set()
            for org in self.organizations:
                organization_keys.add(str(org.id))
                if getattr(org, "uuid", None):
                    organization_keys.add(org.uuid)

            unknown_keys = [
                key for key in self.roles.keys() if key not in organization_keys
            ]
            if unknown_keys:
                raise ValidationError(
                    "roles contains keys that are not in organizations: "
                    + ", ".join(unknown_keys)
                )

        if self.is_organisation_admin and self.roles:
            has_admin_role = any("admin" in roles for roles in self.roles.values())
            if not has_admin_role:
                raise ValidationError(
                    "is_organisation_admin cannot be true when no organization has admin role"
                )

    def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)
