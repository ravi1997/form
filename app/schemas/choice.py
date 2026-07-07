from __future__ import annotations

from typing import Optional

from app.schemas.common import SchemaModel


class ChoiceBase(SchemaModel):
    label: str
    value: str
    visibility_condition: Optional[str] = None


class ChoiceCreateInput(ChoiceBase):
    uuid: str


class ChoiceUpdateInput(SchemaModel):
    label: Optional[str] = None
    value: Optional[str] = None
    visibility_condition: Optional[str] = None


class ChoiceRef(SchemaModel):
    uuid: str
    value: str


class ChoiceOutput(ChoiceBase):
    uuid: str
