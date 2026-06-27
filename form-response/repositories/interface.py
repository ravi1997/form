from __future__ import annotations

from abc import ABC, abstractmethod

from models.core import FormSnapshot, ResponseRecord


class RepositoryInterface(ABC):
    @abstractmethod
    def get_form(self, form_id: str, snapshot_version: int | None = None) -> FormSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_form(self, form: FormSnapshot) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_forms(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_response(self, response_id: str) -> ResponseRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_responses_by_form_id(self, form_id: str) -> list[ResponseRecord]:
        raise NotImplementedError

    @abstractmethod
    def upsert_response(self, response: ResponseRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_responses(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        raise NotImplementedError

