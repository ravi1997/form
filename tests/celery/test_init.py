from __future__ import annotations

from app.celery.app import celery_app, init_celery
from app.celery.config import build_celery_config
from app.celery.tasks import enforce_password_expiry_task


def test_password_expiry_task_is_scheduled_in_beat_config():
    config = build_celery_config({})
    beat_schedule = config["beat_schedule"]

    assert "enforce-password-expiry" in beat_schedule
    entry = beat_schedule["enforce-password-expiry"]
    assert entry["task"] == "app.celery.tasks.enforce_password_expiry_task"
    assert getattr(entry["schedule"], "minute", None) == {0}
    assert getattr(entry["schedule"], "hour", None) == {0, 6, 12, 18}


def test_celery_initialization_exposes_app_extension(app):
    assert "celery" in app.extensions
    assert app.extensions["celery"] is celery_app
    assert celery_app.conf.broker_url == app.config["CELERY_BROKER_URL"]


def test_celery_configuration_follows_flask_app_settings(app):
    celery = init_celery(app)
    assert celery.conf.task_default_queue == app.config["CELERY_TASK_DEFAULT_QUEUE"]
    assert celery.conf.task_time_limit == app.config["CELERY_TASK_TIME_LIMIT"]
    assert "enforce-password-expiry" in celery.conf.beat_schedule
    assert (
        celery.conf.beat_schedule["enforce-password-expiry"]["task"]
        == "app.celery.tasks.enforce_password_expiry_task"
    )
    assert "app.celery.tasks.enforce_password_expiry_task" in celery.tasks


def test_password_expiry_task_delegates_to_service(monkeypatch):
    calls = {"count": 0}

    def fake_enforce_password_expiry():
        calls["count"] += 1
        return 3

    monkeypatch.setattr(
        "app.celery.tasks.enforce_password_expiry",
        fake_enforce_password_expiry,
    )

    result = enforce_password_expiry_task.run.__func__(
        type("FakeTask", (), {"request": type("Request", (), {})()})()
    )

    assert calls["count"] == 1
    assert result == {"updated_count": 3}
