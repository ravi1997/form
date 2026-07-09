from __future__ import annotations

import os
from typing import Any, Dict, Optional

from celery import Celery
from celery import Task

from app.celery.config import build_celery_config


celery_app = Celery("form_service", include=["app.celery.tasks"])
celery_app.conf.update(build_celery_config(os.environ))
app = celery_app
_registered = False


class FlaskContextTask(Task):
    """Run Celery tasks inside the active Flask application context."""

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any):
        flask_app = getattr(self, "_flask_app", None)
        if flask_app is None:
            return super().__call__(*args, **kwargs)
        with flask_app.app_context():
            return super().__call__(*args, **kwargs)


def init_celery(flask_app) -> Celery:
    global _registered

    celery_app.conf.update(build_celery_config(flask_app.config))
    FlaskContextTask._flask_app = flask_app
    celery_app.Task = FlaskContextTask
    celery_app.set_default()
    flask_app.extensions["celery"] = celery_app
    if not _registered:
        from app.celery.signals import register_celery_signals

        register_celery_signals(celery_app, flask_app)
        _registered = True
    return celery_app


def create_celery_app(config: Optional[Dict[str, Any]] = None) -> Celery:
    if config:
        celery_app.conf.update(build_celery_config(config))
    return celery_app
