from __future__ import annotations

from app.middleware import observability


def test_options_requests_do_not_affect_metrics(client):
    observability._metrics_state = observability._MetricsState(  # type: ignore[attr-defined]
        started_at_epoch=observability.time.time()
    )

    response = client.options("/api/v1/health")
    assert response.status_code in {200, 204, 405}

    snapshot = observability.get_metrics_snapshot()
    assert snapshot["requests_total"] == 0
    assert snapshot["requests_inflight"] == 0
