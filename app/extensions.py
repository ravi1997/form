from __future__ import annotations

from typing import Any, Dict, cast

import mongoengine as me
from flask import Flask


class MongoEngineCompat:
    """Minimal Flask integration layer for mongoengine."""

    def init_app(self, app: Flask) -> None:
        settings = app.config.get("MONGODB_SETTINGS", {})
        if isinstance(settings, (list, tuple)):
            if not settings:
                raise ValueError("MONGODB_SETTINGS cannot be empty")
            settings = settings[0]
        if not isinstance(settings, dict):
            raise TypeError("MONGODB_SETTINGS must be a mapping")

        config: Dict[str, Any] = dict(settings)
        alias = config.pop("alias", "default")

        # Ensure a clean alias when app factories create multiple test apps.
        try:
            me.disconnect(alias=alias)
        except Exception:
            pass

        me.connect(alias=alias, **config)

    def __getattr__(self, name: str) -> Any:
        return getattr(me, name)


db = cast(Any, MongoEngineCompat())
