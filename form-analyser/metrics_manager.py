"""
metrics_manager.py
------------------
Lightweight distributed Prometheus metrics exporter using Redis.
"""

from __future__ import annotations
import time
from flask import Flask, request, g, Response
from redis import Redis

def setup_metrics(app: Flask):
    """Register request hooks and /metrics endpoint on the Flask app."""
    
    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.after_request
    def record_metrics(response):
        # Skip if timer didn't start or auth/redis is down
        if not hasattr(g, "start_time"):
            return response
            
        duration = time.time() - g.start_time
        redis_url = app.config.get("REDIS_URL")
        if not redis_url:
            return response

        try:
            r = Redis.from_url(redis_url)
            # 1. Increment request counts
            # Key: metrics:requests  Field: POST:/api/analysis/run:200
            path = request.path
            field = f"{request.method}:{path}:{response.status_code}"
            r.hincrby("metrics:requests", field, 1)

            # 2. Record latency sum and count per endpoint
            if request.endpoint:
                r.hincrby("metrics:latency_count", request.endpoint, 1)
                r.hincrbyfloat("metrics:latency_sum", request.endpoint, duration)
        except Exception:
            pass # Fail-safe

        return response

    @app.get("/metrics")
    def prometheus_metrics():
        """Expose Prometheus formatted metric strings."""
        redis_url = app.config.get("REDIS_URL")
        if not redis_url:
            return Response("Redis metrics disabled (no REDIS_URL)", mimetype="text/plain")

        lines = [
            "# HELP http_requests_total Total number of HTTP requests processed.",
            "# TYPE http_requests_total counter"
        ]
        
        try:
            r = Redis.from_url(redis_url)
            
            # Fetch request totals
            reqs = r.hgetall("metrics:requests")
            for field, val in reqs.items():
                # field is e.g. "POST:/api/analysis:201"
                parts = field.decode().split(":")
                method, path, status = parts[0], parts[1], parts[2]
                count = int(val)
                lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

            # Fetch latency counts and sums
            lines.append("# HELP http_request_duration_seconds_sum Latency sum in seconds per endpoint.")
            lines.append("# TYPE http_request_duration_seconds_sum counter")
            sums = r.hgetall("metrics:latency_sum")
            for endpoint, val in sums.items():
                lines.append(f'http_request_duration_seconds_sum{{endpoint="{endpoint.decode()}"}} {float(val):.6f}')

            lines.append("# HELP http_request_duration_seconds_count Total requests timed per endpoint.")
            lines.append("# TYPE http_request_duration_seconds_count counter")
            counts = r.hgetall("metrics:latency_count")
            for endpoint, val in counts.items():
                lines.append(f'http_request_duration_seconds_count{{endpoint="{endpoint.decode()}"}} {int(val)}')
                
        except Exception as e:
            return Response(f"# Error reading metrics: {e}", status=500, mimetype="text/plain")

        return Response("\n".join(lines) + "\n", mimetype="text/plain")
