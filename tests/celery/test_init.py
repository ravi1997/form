from __future__ import annotations

from app.celery.app import celery_app, init_celery


def test_celery_initialization_exposes_app_extension(app):
    assert "celery" in app.extensions
    assert app.extensions["celery"] is celery_app
    assert celery_app.conf.broker_url == app.config["CELERY_BROKER_URL"]


def test_celery_configuration_follows_flask_app_settings(app):
    celery = init_celery(app)
    assert celery.conf.task_default_queue == app.config["CELERY_TASK_DEFAULT_QUEUE"]
    assert celery.conf.task_time_limit == app.config["CELERY_TASK_TIME_LIMIT"]
