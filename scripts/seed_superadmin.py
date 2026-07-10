#!/usr/bin/env python
"""
Superadmin Seeding Script

This script registers a default superadmin user if one does not already exist.
It can be run manually or imported and executed during application startup.

Usage:
    python scripts/seed_superadmin.py
"""

import os
import sys
from uuid import uuid4
from werkzeug.security import generate_password_hash

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.user import User
from app.utils import utcnow
from mongoengine.errors import NotUniqueError


def seed_superadmin(app=None):
    """Seed a default superadmin user if none exists."""
    # If app is passed, use its context; otherwise, create an app instance
    if app is None:
        from app import create_openapi_app
        app = create_openapi_app()

    with app.app_context():
        # Load credentials from environment or use defaults
        name = os.environ.get("SUPERADMIN_NAME", "Super Admin").strip()
        email = os.environ.get("SUPERADMIN_EMAIL", "admin@example.com").strip().lower()
        password = os.environ.get("SUPERADMIN_PASSWORD", "admin123")

        # Check if any superadmin already exists
        existing_superadmin = User.objects(is_super_admin=True).first()
        if existing_superadmin:
            app.logger.info("Superadmin already exists: %s", existing_superadmin.email)
            return False, existing_superadmin

        # Check if the specific email is already registered by a non-superadmin
        existing_user = User.objects(email=email).first()
        if existing_user:
            # Promote existing user to superadmin
            existing_user.is_super_admin = True
            try:
                existing_user.save()
                app.logger.info("Promoted existing user to superadmin: %s", email)
                return True, existing_user
            except NotUniqueError:
                pass

        # Create new superadmin
        now = utcnow()
        superadmin = User(
            uuid=str(uuid4()),
            name=name,
            email=email,
            auth_provider="local",
            password_hash=generate_password_hash(password),
            created_at=now,
            updated_at=now,
            is_super_admin=True,
            is_email_verified=True,
            status="active"
        )
        try:
            superadmin.save()
            app.logger.info("Successfully seeded superadmin: %s", email)
            return True, superadmin
        except NotUniqueError:
            # Concurrent worker initialized the same email first
            existing = User.objects(email=email).first()
            if existing:
                app.logger.info("Superadmin registered concurrently: %s", email)
                return False, existing
            raise


if __name__ == "__main__":
    try:
        success, user = seed_superadmin()
        if success:
            print(f"✓ Created/promoted superadmin: {user.email}")
            sys.exit(0)
        else:
            print(f"⊘ Superadmin already exists: {user.email}")
            sys.exit(0)
    except Exception as exc:
        print(f"✗ Error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
