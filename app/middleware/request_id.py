from __future__ import annotations

from uuid import uuid4

from flask import g, request

from app.config import BaseConfig


def register_request_id_middleware(app) -> None:
    """Attach request correlation IDs to request context and responses."""

    @app.before_request
    def assign_request_id():
        header_name = BaseConfig.get_str(
            app.config,
            "REQUEST_ID_HEADER",
            BaseConfig.REQUEST_ID_HEADER,
        )
        incoming = request.headers.get(header_name)
        request_id = incoming.strip() if incoming and incoming.strip() else str(uuid4())
        g.request_id = request_id
        g.request_id_header = header_name

    @app.after_request
    def inject_request_id_header(response):
        request_id = getattr(g, "request_id", None)
        header_name = getattr(g, "request_id_header", BaseConfig.REQUEST_ID_HEADER)
        if request_id:
            response.headers[header_name] = request_id
        return response
