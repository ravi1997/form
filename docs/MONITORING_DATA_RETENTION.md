# Monitoring Data Retention

Condition evaluation statistics are retained in MongoDB for a bounded period.
The retention window is configured with `MONITORING_STATS_RETENTION_DAYS` and
defaults to 30 days.

## Strategy

- Raw evaluation stats are kept for short-term operational visibility.
- MongoDB TTL removes records older than the configured retention window.
- Dashboards and rolling metrics should use the recent window rather than raw
  historical events.

## Operational notes

- The TTL index is applied when the application initializes.
- Increase the retention window only if a concrete reporting need exists.
- A longer retention period should be paired with an archival plan if the
  collection growth starts impacting storage or query performance.

## Verification

- Check `ConditionEvaluationStat` collection indexes for a TTL index on
  `created_at`.
- Confirm the configured retention window in app config or environment.
- Validate that old records disappear after the configured TTL interval.
