from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict

from flask import Response, g, request


@dataclass
class _MetricsState:
    started_at_epoch: float = field(default_factory=time.time)
    requests_total: int = 0
    requests_inflight: int = 0
    request_duration_ms_sum: float = 0.0
    responses_by_status: Dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )


_metrics_state = _MetricsState()
_metrics_lock = threading.Lock()


def _is_origin_allowed(origin: str | None, allowed_origins: list[str]) -> bool:
    if not origin:
        return False
    if "*" in allowed_origins:
        return True
    return origin in allowed_origins


def register_observability_middleware(app) -> None:
    @app.before_request
    def _before_request_metrics() -> None:
        g.request_started_monotonic = time.perf_counter()
        with _metrics_lock:
            _metrics_state.requests_inflight += 1

    @app.after_request
    def _after_request_metrics_and_headers(response: Response) -> Response:
        duration_ms = 0.0
        started = getattr(g, "request_started_monotonic", None)
        if started is not None:
            duration_ms = (time.perf_counter() - started) * 1000

        with _metrics_lock:
            _metrics_state.requests_total += 1
            _metrics_state.requests_inflight = max(
                0, _metrics_state.requests_inflight - 1
            )
            _metrics_state.request_duration_ms_sum += duration_ms
            _metrics_state.responses_by_status[str(response.status_code)] += 1

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "0")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        allowed_origins = list(app.config.get("CORS_ALLOW_ORIGINS") or [])
        origin = request.headers.get("Origin")
        if _is_origin_allowed(origin, allowed_origins):
            allow_any = "*" in allowed_origins
            response.headers["Access-Control-Allow-Origin"] = (
                "*" if allow_any else (origin or "")
            )
            response.headers["Vary"] = "Origin"
            if not allow_any:
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Request-Id"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )

        return response


def get_metrics_snapshot() -> dict:
    with _metrics_lock:
        avg_duration = (
            _metrics_state.request_duration_ms_sum / _metrics_state.requests_total
            if _metrics_state.requests_total
            else 0.0
        )
        return {
            "uptime_seconds": int(time.time() - _metrics_state.started_at_epoch),
            "requests_total": _metrics_state.requests_total,
            "requests_inflight": _metrics_state.requests_inflight,
            "average_request_duration_ms": round(avg_duration, 4),
            "responses_by_status": dict(_metrics_state.responses_by_status),
        }
