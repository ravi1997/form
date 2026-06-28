"""
seed_all.py
-----------
Unified database seeding script for the unified-form-service.

Combines:
  - Form builder data seeding (themes, forms, users, organizations)
  - Form analyser demo responses data seeding (responses, analytics definitions)

Run with:
    python seed_all.py [--builder] [--analyser] [--all]

Flags:
  --builder   Seed only builder data (themes, forms, orgs)
  --analyser  Seed only analyser demo responses
  --all       (default) Seed all data
"""

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

from config import active_config


# ---------------------------------------------------------------------------
# Shared Setup
# ---------------------------------------------------------------------------

def get_mongo_client():
    mongo_uri = getattr(active_config, "MONGO_URI", "mongodb://localhost:27017/")
    return MongoClient(mongo_uri)


# ---------------------------------------------------------------------------
# Builder Seeding (via Flask test client)
# ---------------------------------------------------------------------------

def seed_builder():
    print("\n" + "=" * 60)
    print("  SEEDING FORM BUILDER DATA")
    print("=" * 60)

    try:
        from app import app
    except ImportError as e:
        print(f"[ERROR] Could not import app: {e}")
        return

    client = app.test_client()

    # Step 1: Create a Theme
    print("\n[1/4] Creating Theme Template...")
    theme_payload = {
        "name": "Midnight Ocean",
        "active": True,
        "style": {
            "font_family": "Outfit, sans-serif",
            "background_gradient": "linear-gradient(135deg, #0f2027, #203a43, #2c5364)",
            "primary_color": "#00d2ff",
            "secondary_color": "#00d2ff",
            "surface_color": "rgba(255, 255, 255, 0.05)",
            "text_color": "#ffffff",
            "border_radius": "12px",
            "backdrop_blur": "10px",
            "animation_speed": "0.3s"
        }
    }
    theme_res = client.post("/api/themes", json=theme_payload)
    theme_data = json.loads(theme_res.data)
    print(f"    ✓ Theme Created: {theme_data.get('_id', 'N/A')}")

    # Step 2: Create Organization
    print("\n[2/4] Creating Demo Organization...")
    org_payload = {
        "name": "Demo Corp",
        "plan": "enterprise",
        "admin_email": "admin@democorp.com"
    }
    org_res = client.post("/api/organizations", json=org_payload)
    if org_res.status_code in (200, 201):
        org_data = json.loads(org_res.data)
        org_id = org_data.get("_id", "demo_org_001")
        print(f"    ✓ Organization Created: {org_id}")
    else:
        org_id = "demo_org_001"
        print(f"    ! Organization endpoint unavailable, using placeholder: {org_id}")

    # Step 3: Create a Form
    print("\n[3/4] Creating Sample Customer Feedback Form...")
    form_payload = {
        "title": "Customer Satisfaction Survey",
        "organization_id": org_id,
        "fields": [
            {"type": "text",   "label": "Full Name",  "variable_name": "full_name",  "required": True},
            {"type": "email",  "label": "Email",      "variable_name": "email",      "required": True},
            {"type": "rating", "label": "Rating",     "variable_name": "rating",     "required": True, "max": 5},
            {"type": "textarea","label": "Feedback",  "variable_name": "feedback",   "required": False},
            {"type": "select", "label": "Department", "variable_name": "department", "required": True,
             "options": ["Sales", "Support", "Engineering", "Product"]}
        ]
    }
    form_res = client.post("/api/forms", json=form_payload)
    if form_res.status_code in (200, 201):
        form_data = json.loads(form_res.data)
        form_id = form_data.get("_id", "demo_form_001")
        print(f"    ✓ Form Created: {form_id}")
    else:
        form_id = "demo_form_001"
        print(f"    ! Form endpoint unavailable, using placeholder: {form_id}")

    # Step 4: Register Demo User
    print("\n[4/4] Registering Demo Admin User...")
    user_payload = {
        "email": "admin@democorp.com",
        "password": "SecurePass123!",
        "name": "Demo Admin",
        "organization_id": org_id,
        "roles": ["admin"]
    }
    user_res = client.post("/api/auth/register", json=user_payload)
    if user_res.status_code in (200, 201):
        print(f"    ✓ Demo Admin User registered.")
    else:
        print(f"    ! User registration endpoint unavailable (may already exist).")

    print("\n✅ Builder seeding complete.")


# ---------------------------------------------------------------------------
# Analyser Seeding (direct MongoDB writes)
# ---------------------------------------------------------------------------

DEMO_ORG_ID  = "org_demo_001"
DEMO_FORM_ID = "form_demo_" + str(uuid.uuid4())
DEMO_FV_ID   = "fv_demo_"   + str(uuid.uuid4())
NUM_RESPONSES = 200

DEPARTMENTS  = ["Sales", "Support", "Engineering", "Product"]
STATUSES     = ["submitted", "submitted", "submitted", "draft"]  # weighted


def _random_response():
    submitted_at = datetime.now(timezone.utc) - timedelta(
        days=random.randint(0, 60),
        hours=random.randint(0, 23)
    )
    return {
        "organization_id": DEMO_ORG_ID,
        "form": {
            "id":      DEMO_FORM_ID,
            "version": DEMO_FV_ID,
            "title":   "Customer Satisfaction Survey",
        },
        "form_id":      DEMO_FORM_ID,
        "survey_id":    DEMO_FORM_ID,
        "response_id":  str(uuid.uuid4()),
        "status":       random.choice(STATUSES),
        "submitted_at": submitted_at,
        "inserted_at":  datetime.now(timezone.utc),
        "data": {
            "full_name":   random.choice(["Alice", "Bob", "Carol", "David", "Eve",
                                          "Frank", "Grace", "Henry", "Iris", "Jack"]),
            "email":       f"user{random.randint(1,999)}@example.com",
            "rating":      random.randint(1, 5),
            "feedback":    random.choice([
                "Great service!", "Could be better.", "Very satisfied.",
                "Will recommend.", "Average experience.", "Excellent support!",
                None
            ]),
            "department":  random.choice(DEPARTMENTS),
        },
        "answers": {
            "full_name":  random.choice(["Alice", "Bob", "Carol"]),
            "email":      f"user{random.randint(1,999)}@example.com",
            "rating":     random.randint(1, 5),
            "department": random.choice(DEPARTMENTS),
        },
    }


def seed_analyser():
    print("\n" + "=" * 60)
    print("  SEEDING FORM ANALYSER DEMO RESPONSES")
    print("=" * 60)

    mongo_client = get_mongo_client()
    db_name = getattr(active_config, "MONGO_DB_NAME", "form_analyser")
    db = mongo_client[db_name]

    col_name = getattr(active_config, "RESPONSES_COLLECTION", "responses")
    col = db[col_name]

    print(f"\n[1/2] Inserting {NUM_RESPONSES} demo responses into '{db_name}.{col_name}'...")
    docs = [_random_response() for _ in range(NUM_RESPONSES)]
    result = col.insert_many(docs)
    print(f"    ✓ Inserted {len(result.inserted_ids)} responses.")

    print("\n[2/2] Creating demo analytics definition document...")
    definitions_col = db.get_collection(
        getattr(active_config, "DEFINITIONS_COLLECTION", "survey_definitions")
    )
    existing = definitions_col.find_one({"survey_id": DEMO_FORM_ID})
    if not existing:
        definitions_col.insert_one({
            "survey_id":   DEMO_FORM_ID,
            "title":       "Customer Satisfaction Survey",
            "description": "Demo analytics definition for seeded data",
            "created_at":  datetime.now(timezone.utc),
            "questions": [
                {"id": "q_rating",     "type": "rating",  "variable_name": "rating",     "label": "Rating"},
                {"id": "q_dept",       "type": "select",  "variable_name": "department", "label": "Department"},
                {"id": "q_full_name",  "type": "text",    "variable_name": "full_name",  "label": "Full Name"},
                {"id": "q_feedback",   "type": "textarea","variable_name": "feedback",   "label": "Feedback"},
            ]
        })
        print(f"    ✓ Analytics definition created for form: {DEMO_FORM_ID}")
    else:
        print(f"    ! Analytics definition already exists, skipping.")

    mongo_client.close()
    print("\n✅ Analyser seeding complete.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified database seeder for unified-form-service."
    )
    parser.add_argument("--builder",  action="store_true", help="Seed builder data only")
    parser.add_argument("--analyser", action="store_true", help="Seed analyser data only")
    parser.add_argument("--all",      action="store_true", help="Seed all data (default)")
    args = parser.parse_args()

    run_all      = args.all or (not args.builder and not args.analyser)
    run_builder  = args.builder  or run_all
    run_analyser = args.analyser or run_all

    if run_builder:
        seed_builder()

    if run_analyser:
        seed_analyser()

    print("\n" + "=" * 60)
    print("  ALL SEEDING COMPLETE ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
