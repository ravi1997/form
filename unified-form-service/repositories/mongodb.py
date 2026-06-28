from __future__ import annotations
import json
from dataclasses import asdict
from pymongo import MongoClient
from pymongo.database import Database
from models.core import FormSnapshot, ResponseRecord
from repositories.interface import RepositoryInterface


class MongoDBRepository(RepositoryInterface):
    def __init__(self, database_url: str = "mongodb://localhost:27017/form_response", client: MongoClient | None = None):
        self.database_url = database_url
        self.client: MongoClient = client if client is not None else MongoClient(database_url)
        # Extract db name from database_url or default to form_response
        db_name = "form_response"
        if "/" in database_url.replace("mongodb://", ""):
            parts = database_url.split("/")
            if parts[-1] and "?" not in parts[-1]:
                db_name = parts[-1]
            elif parts[-1] and "?" in parts[-1]:
                db_name = parts[-1].split("?")[0]
        self.db: Database = self.client[db_name]

    def initialize(self) -> None:
        # Create unique index for forms
        self.db.forms.create_index([("form_id", 1), ("snapshot_version", 1)], unique=True)
        # Create index for responses
        self.db.responses.create_index("form_id")
        self.db.responses.create_index("status")

    def health_check(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def clear_forms(self) -> None:
        self.db.forms.delete_many({})

    def clear_responses(self) -> None:
        self.db.responses.delete_many({})

    def get_form(self, form_id: str, snapshot_version: int | None = None) -> FormSnapshot | None:
        if snapshot_version is not None:
            doc = self.db.forms.find_one({"form_id": form_id, "snapshot_version": snapshot_version})
        else:
            doc = self.db.forms.find_one({"form_id": form_id}, sort=[("snapshot_version", -1)])
        if not doc:
            return None
        payload = json.loads(doc["payload"])
        return FormSnapshot(**payload)

    def upsert_form(self, form: FormSnapshot) -> None:
        payload = json.dumps(asdict(form))
        self.db.forms.update_one(
            {"form_id": form.form_id, "snapshot_version": form.snapshot_version},
            {"$set": {
                "payload": payload,
                "updated_at": form.updated_at
            }},
            upsert=True
        )

    def get_response(self, response_id: str) -> ResponseRecord | None:
        doc = self.db.responses.find_one({"_id": response_id})
        if not doc:
            return None
        payload = json.loads(doc["payload"])
        return ResponseRecord(**payload)

    def list_responses_by_form_id(self, form_id: str) -> list[ResponseRecord]:
        cursor = self.db.responses.find({"form_id": form_id}).sort("updated_at", -1)
        results = []
        for doc in cursor:
            payload = json.loads(doc["payload"])
            results.append(ResponseRecord(**payload))
        return results

    def upsert_response(self, response: ResponseRecord) -> None:
        payload = json.dumps(asdict(response))
        self.db.responses.update_one(
            {"_id": response.response_id},
            {"$set": {
                "form_id": response.form_id,
                "payload": payload,
                "status": response.status,
                "submitted_at": response.submitted_at,
                "updated_at": response.updated_at
            }},
            upsert=True
        )
