"""
locustfile.py — Load tests for the Unified Form Service
========================================================
Covers:
  - POST /api/auth/login          (weight 1 — runs once per user on start)
  - GET  /api/forms               (weight 5 — read-heavy browsing)
  - POST /api/forms/<id>/submit   (weight 2 — occasional submissions)

Run via docker-compose dev stack:
  docker compose -f docker-compose.dev.yml up locust

Or directly:
  locust -f locustfile.py --host=http://localhost:5000

Env vars (optional, override defaults):
  LOCUST_USERNAME   — login username  (default: testuser@example.com)
  LOCUST_PASSWORD   — login password  (default: testpassword)
  LOCUST_FORM_ID    — fixed form ID to submit; if unset a random one from
                      GET /api/forms is used each iteration
"""

import os
import random
import string
import logging

from locust import HttpUser, task, between, events

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_USERNAME = os.getenv("LOCUST_USERNAME", "testuser@example.com")
DEFAULT_PASSWORD = os.getenv("LOCUST_PASSWORD", "testpassword")
FIXED_FORM_ID = os.getenv("LOCUST_FORM_ID", "")  # empty → discover dynamically


def _random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _random_email() -> str:
    return f"{_random_string()}@example.com"


# ---------------------------------------------------------------------------
# FormServiceUser
# ---------------------------------------------------------------------------
class FormServiceUser(HttpUser):
    """
    Simulates a user who:
      1. Logs in on start (token cached for the session lifetime).
      2. Browses the forms list frequently.
      3. Occasionally submits a form response.
    """

    # Think-time between tasks: 1–5 seconds (realistic browsing pace)
    wait_time = between(1, 5)

    # Instance-level state
    auth_token: str = ""
    available_form_ids: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Called once per simulated user when it starts."""
        self._login()
        if not self.auth_token:
            # Cannot proceed without auth — stop this user
            self.environment.runner.quit()
            return
        # Pre-fetch the form list so submit tasks have IDs to work with
        self._fetch_forms()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _login(self) -> None:
        """POST /api/auth/login and cache the JWT token."""
        payload = {
            "email": DEFAULT_USERNAME,
            "password": DEFAULT_PASSWORD,
        }
        with self.client.post(
            "/api/auth/login",
            json=payload,
            name="POST /api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                # Support both {"token": "..."} and {"access_token": "..."}
                self.auth_token = data.get("token") or data.get("access_token", "")
                if self.auth_token:
                    resp.success()
                    logger.debug("Login successful, token acquired.")
                else:
                    resp.failure("Login response did not contain a token.")
            else:
                resp.failure(
                    f"Login failed: HTTP {resp.status_code} — {resp.text[:200]}"
                )

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.auth_token}"}

    # ------------------------------------------------------------------
    # Task helpers
    # ------------------------------------------------------------------

    def _fetch_forms(self) -> None:
        """GET /api/forms — populate available_form_ids for submit tasks."""
        with self.client.get(
            "/api/forms",
            headers=self._auth_headers,
            name="GET /api/forms",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                # Handle both list and {"forms": [...]} response shapes
                forms = data if isinstance(data, list) else data.get("forms", [])
                self.available_form_ids = [
                    str(f.get("id") or f.get("_id") or f.get("form_id", ""))
                    for f in forms
                    if f.get("id") or f.get("_id") or f.get("form_id")
                ]
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized — re-attempting login.")
                self._login()
            else:
                resp.failure(f"GET /api/forms returned HTTP {resp.status_code}")

    def _pick_form_id(self) -> str:
        """Return a form ID to use for a submit task."""
        if FIXED_FORM_ID:
            return FIXED_FORM_ID
        if self.available_form_ids:
            return random.choice(self.available_form_ids)
        return "unknown-form-id"

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task(5)
    def list_forms(self) -> None:
        """GET /api/forms — high-frequency browsing task."""
        with self.client.get(
            "/api/forms",
            headers=self._auth_headers,
            name="GET /api/forms",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
                # Opportunistically refresh available IDs
                data = resp.json()
                forms = data if isinstance(data, list) else data.get("forms", [])
                if forms:
                    self.available_form_ids = [
                        str(f.get("id") or f.get("_id") or f.get("form_id", ""))
                        for f in forms
                        if f.get("id") or f.get("_id") or f.get("form_id")
                    ]
            elif resp.status_code == 401:
                resp.failure("Unauthorized on GET /api/forms — re-logging in.")
                self._login()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def submit_form(self) -> None:
        """POST /api/forms/<form_id>/submit — realistic form submission."""
        form_id = self._pick_form_id()

        # Build a realistic-looking submission payload
        payload = {
            "respondent_email": _random_email(),
            "respondent_name": f"{_random_string(5).capitalize()} {_random_string(7).capitalize()}",
            "responses": {
                "name": _random_string(6).capitalize(),
                "email": _random_email(),
                "message": (
                    "This is an automated load-test submission. "
                    f"Random token: {_random_string(12)}"
                ),
                "rating": random.randint(1, 5),
                "agree_to_terms": True,
            },
            "metadata": {
                "source": "locust-load-test",
                "user_agent": "Locust/2.x",
            },
        }

        with self.client.post(
            f"/api/forms/{form_id}/submit",
            json=payload,
            headers=self._auth_headers,
            name="POST /api/forms/<form_id>/submit",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized on submit — re-logging in.")
                self._login()
            elif resp.status_code == 404:
                # Form ID not found — silently mark as failure but don't quit
                resp.failure(f"Form {form_id!r} not found (404).")
            elif resp.status_code == 422:
                # Validation error — log body for debugging
                resp.failure(
                    f"Validation error on submit (422): {resp.text[:300]}"
                )
            else:
                resp.failure(
                    f"Unexpected response {resp.status_code}: {resp.text[:200]}"
                )

    @task(1)
    def login_refresh(self) -> None:
        """
        Periodically re-authenticate to simulate token expiry / session renewal.
        Lower weight keeps this infrequent relative to browsing.
        """
        self._login()


# ---------------------------------------------------------------------------
# Event hooks (optional — wire into CI or custom reporters here)
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info(
        "Locust load test starting — target host: %s", environment.host
    )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("Locust load test finished.")
