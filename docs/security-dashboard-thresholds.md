# Security Dashboard Thresholds

This document defines starter alert thresholds for authentication and session security telemetry.

## Scope

- Source events: structured `security_event` logs and session audit records.
- Aggregation windows: 1 minute (spike), 5 minutes (sustained), 1 hour (trend).
- Dimensions: global, per user UUID, per IP, per organization (if available).

## Alert Rules

1. Authentication failures spike
- Signal: `event=login` with `outcome=failed`.
- Trigger (warning): >= 20 failures in 5 minutes from one IP.
- Trigger (critical): >= 60 failures in 5 minutes from one IP.
- Trigger (critical): >= 10 failed logins for one user in 5 minutes.

2. Throttle spike by IP or user
- Signal: `event=rate_limit` with `outcome=throttled`.
- Trigger (warning): >= 50 throttles in 5 minutes for one IP.
- Trigger (critical): >= 150 throttles in 5 minutes for one IP.
- Trigger (warning): >= 20 throttles in 5 minutes for one user.
- Trigger (critical): >= 75 throttles in 5 minutes for one user.

3. Unusual admin revocation volume
- Signal: `event in {admin_session_revoke, admin_sessions_revoke_all}` with `outcome=success`.
- Trigger (warning): >= 25 revoked sessions in 10 minutes by one admin.
- Trigger (critical): >= 100 revoked sessions in 10 minutes by one admin.
- Trigger (critical): >= 3 distinct admins performing revoke-all within 15 minutes.

4. Audit query latency or volume anomalies
- Signal: admin audit endpoints request duration and query volume.
- Trigger (warning): p95 latency >= 800ms for 5 minutes.
- Trigger (critical): p95 latency >= 1500ms for 5 minutes.
- Trigger (warning): > 300 audit queries in 5 minutes globally.
- Trigger (critical): > 1000 audit queries in 5 minutes globally.

## Runbook Notes

- Validate request burst source with request ID and IP correlation.
- For user-centric spikes, inspect active sessions and recent refresh/logout activity.
- For admin spikes, verify change window or incident response activity before enforcement.
- Tune thresholds after one week of baseline traffic observation.
