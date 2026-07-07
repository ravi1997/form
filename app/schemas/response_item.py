from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field

from app.schemas.common import SchemaModel


class ResponseItemBase(SchemaModel):
    question_uuid: str
    section_uuid: Optional[str] = None
    repeat_index: Optional[int] = Field(default=None, ge=0)
    value: Optional[Any] = None
    value_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResponseItemCreateInput(ResponseItemBase):
    pass


class ResponseItemUpdateInput(SchemaModel):
    section_uuid: Optional[str] = None
    repeat_index: Optional[int] = Field(default=None, ge=0)
    value: Optional[Any] = None
    value_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ResponseItemOutput(ResponseItemBase):
    pass
