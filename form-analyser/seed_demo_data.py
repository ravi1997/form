"""
seed_demo_data.py
-----------------
Inserts sample form responses into MongoDB matching the real form-backend schema.

The key difference from generic demo data:
  - Answers live inside the `data` dict (keys = question variable_names)
  - Top-level fields mirror FormResponse model: organization_id, form, status, etc.
  - Multi-select answers stored as arrays (to exercise array_frequency step type)

Run with:
    python seed_demo_data.py
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

from config import active_config

# ---------------------------------------------------------------------------
# Demo identifiers — replace with real UUIDs from your database
# ---------------------------------------------------------------------------
DEMO_ORG_ID   = "org_demo_001"
DEMO_FORM_ID  = "form_demo_" + str(uuid.uuid4())   # stable per seed run
DEMO_FV_ID    = "fv_demo_"   + str(uuid.uuid4())

NUM_RESPONSES = 200

# ---------------------------------------------------------------------------
# Question variable_names and their answer options
# (mirrors what you'd define in Form → Section → Question.variable_name)
# ---------------------------------------------------------------------------

SATISFACTION_FIELD  = "satisfaction_rating"   # radio / select
RATING_FIELD        = "overall_rating"        # number / rating (1-5)
NPS_FIELD           = "nps_score"             # number (0-10)
REGION_FIELD        = "region"                # select / dropdown
AGE_GROUP_FIELD     = "age_group"             # radio
MAIN_ISSUE_FIELD    = "main_issue"            # radio (only for dissatisfied)
FEATURES_FIELD      = "preferred_features"    # multi_select / checkboxes → ARRAY
PHONE_FIELD         = "contact_phone"         # input (intentionally missing ~30%)
STATUS_FIELD        = "status"                # top-level FormResponse field

SATISFACTION_OPTIONS = [
    "Very Satisfied", "Satisfied", "Neutral",
    "Dissatisfied", "Very Dissatisfied",
]
REGION_OPTIONS    = ["North", "South", "East", "West"]
AGE_GROUP_OPTIONS = ["18-24", "25-34", "35-44", "45-54", "55+"]
ISSUE_OPTIONS     = [
    "Long wait times", "Poor communication", "Product quality",
    "Pricing", "Delivery delays", "Technical issues",
    "Customer service", "Billing errors",
]
FEATURE_OPTIONS = [
    "Speed", "Ease of use", "Customer support",
    "Pricing", "Integrations", "Mobile app", "Reporting",
]


def _random_features() -> list[str]:
    """Return 1–3 randomly chosen features (simulates multi-select answer)."""
    k = random.randint(1, 3)
    return random.sample(FEATURE_OPTIONS, k)


def generate_response(idx: int) -> dict:
    satisfaction = random.choices(
        SATISFACTION_OPTIONS,
        weights=[30, 35, 15, 12, 8],
    )[0]

    rating_map = {
        "Very Satisfied": 5, "Satisfied": 4, "Neutral": 3,
        "Dissatisfied": 2,   "Very Dissatisfied": 1,
    }
    base_rating = rating_map[satisfaction]
    rating = max(1, min(5, base_rating + random.randint(-1, 1)))
    nps    = random.randint(0, 10)
    region    = random.choice(REGION_OPTIONS)
    age_group = random.choice(AGE_GROUP_OPTIONS)

    # main_issue only filled in for unhappy respondents
    main_issue = (
        random.choice(ISSUE_OPTIONS)
        if satisfaction in ("Dissatisfied", "Very Dissatisfied", "Neutral")
        else None
    )

    # Phone intentionally missing ~30% of the time → tests "missing" step
    phone = (
        f"+91-9{random.randint(100000000, 999999999)}"
        if random.random() > 0.3 else None
    )

    submitted_at = datetime.now(timezone.utc) - timedelta(
        days=random.randint(0, 90)
    )

    review_status = random.choices(
        ["pending", "approved", "rejected"],
        weights=[50, 40, 10],
    )[0]

    status = random.choices(
        ["submitted", "processed", "approved", "rejected"],
        weights=[40, 30, 20, 10],
    )[0]

    return {
        # --- Top-level FormResponse fields ---
        "organization_id": DEMO_ORG_ID,
        "form":            DEMO_FORM_ID,
        "form_version":    DEMO_FV_ID,
        "version":         "1.0.0",
        "project":         None,

        # --- The answer payload (keys = question variable_names) ---
        "data": {
            SATISFACTION_FIELD: satisfaction,
            RATING_FIELD:       rating,
            NPS_FIELD:          nps,
            REGION_FIELD:       region,
            AGE_GROUP_FIELD:    age_group,
            MAIN_ISSUE_FIELD:   main_issue,
            FEATURES_FIELD:     _random_features(),   # array field
            PHONE_FIELD:        phone,
        },

        # --- Submission metadata ---
        "submitted_by":  f"user_{idx:04d}",
        "submitted_at":  submitted_at,
        "ip_address":    f"192.168.1.{random.randint(1, 254)}",
        "user_agent":    "Mozilla/5.0 (demo seed)",

        # --- Status tracking ---
        "status":        status,
        "review_status": review_status,
        "is_draft":      False,
        "is_deleted":    False,
        "deleted_at":    None,

        # --- Extras ---
        "tags":       [],
        "meta_data":  {},
        "ai_results": {},
        "status_log": [],
    }


def main():
    client = MongoClient(active_config.MONGO_URI)
    db  = client[active_config.MONGO_DB_NAME]
    col = db[active_config.FORM_RESPONSES_COLLECTION]

    # Clear only our demo data (scoped to DEMO_ORG_ID so real data is safe)
    deleted = col.delete_many({"organization_id": DEMO_ORG_ID})
    print(f"Cleared {deleted.deleted_count} existing demo responses.")

    docs   = [generate_response(i) for i in range(1, NUM_RESPONSES + 1)]
    result = col.insert_many(docs)

    print(f"Inserted {len(result.inserted_ids)} demo responses.")
    print(f"  collection    : {active_config.FORM_RESPONSES_COLLECTION}")
    print(f"  organization  : {DEMO_ORG_ID}")
    print(f"  form UUID     : {DEMO_FORM_ID}")
    print()
    print("Use these filters in your analysis definition:")
    print(f'  {{ "field": "form",            "operator": "eq", "value": "{DEMO_FORM_ID}" }}')
    print(f'  {{ "field": "organization_id", "operator": "eq", "value": "{DEMO_ORG_ID}" }}')
    print(f'  {{ "field": "is_deleted",      "operator": "eq", "value": false }}')
    print()
    print("Question variable_names in the data dict:")
    for name in [SATISFACTION_FIELD, RATING_FIELD, NPS_FIELD, REGION_FIELD,
                 AGE_GROUP_FIELD, MAIN_ISSUE_FIELD, FEATURES_FIELD, PHONE_FIELD]:
        print(f"  data.{name}")


if __name__ == "__main__":
    main()
