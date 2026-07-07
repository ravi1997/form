from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.schemas.common import SchemaModel

VersionStatus = Literal["published", "archived", "deleted", "draft", "disabled"]


class VersionBase(SchemaModel):
    major: int = Field(default=0, ge=0)
    minor: int = Field(default=0, ge=0)
    patch: int = Field(default=0, ge=0)
    status: VersionStatus = "draft"


class VersionCreateInput(VersionBase):
    uuid: str
    created_by: Optional[str] = None


class VersionUpdateInput(SchemaModel):
    major: Optional[int] = Field(default=None, ge=0)
    minor: Optional[int] = Field(default=None, ge=0)
    patch: Optional[int] = Field(default=None, ge=0)
    updated_by: Optional[str] = None
    status: Optional[VersionStatus] = None


class VersionRef(SchemaModel):
    uuid: str


class VersionOutput(VersionBase):
    uuid: str
    created: datetime
    created_by: Optional[str] = None
    updated: Optional[datetime] = None
    updated_by: Optional[str] = None
