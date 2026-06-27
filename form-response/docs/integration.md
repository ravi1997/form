# Integration Notes

## Builder contract

The builder should send a form object with:

- `id`
- `title`
- `sections`
- `questions`
- question `id`, `type`, `required`, and any choice metadata needed for validation

This service stores only a minimal snapshot:

- form identity
- title
- sections/question layout
- required flags
- choice metadata needed for validation

## Response contract

Responses are stored with:

- `response_id`
- `form_id`
- `answers`
- `status`
- timestamps

## Analyser adapter

The analyser sync adapter converts internal storage into:

- `form_id`
- `response_id`
- `form_snapshot_version`
- `status`
- `submitted_at`
- `answers`

The adapter is isolated in `services/analyser_adapter.py` so future adapters can be added
without changing routes or repositories.

