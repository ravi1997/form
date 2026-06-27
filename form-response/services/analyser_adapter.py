from __future__ import annotations


def to_analyser_payload(form_snapshot: dict, response: dict) -> dict:
    return {
        "form_id": form_snapshot["form_id"],
        "survey_id": form_snapshot["form_id"],  # Compatibility with form-analyser id_field
        "response_id": response["response_id"],
        "form_snapshot_version": form_snapshot.get("snapshot_version", 1),
        "status": response["status"],
        "submitted_at": response.get("submitted_at"),
        "answers": response["answers"],
        "data": response["answers"],            # Compatibility with form-analyser data subdocument
    }


class AnalyserSyncService:
    def __init__(self):
        self.last_payload: dict | None = None

    def sync(self, form_snapshot: dict, response: dict) -> dict:
        payload = to_analyser_payload(form_snapshot, response)
        self.last_payload = payload
        return {"synced": True, "payload": payload}

