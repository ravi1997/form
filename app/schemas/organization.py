from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from app.schemas.common import SchemaModel

OrganizationStatus = Literal["active", "inactive", "deleted"]


class OrganizationBase(SchemaModel):
    name: str
    admins: List[str] = Field(default_factory=list)
    status: OrganizationStatus = "active"


class OrganizationCreateInput(OrganizationBase):
    uuid: str


class OrganizationUpdateInput(SchemaModel):
    name: Optional[str] = None
    admins: Optional[List[str]] = None
    status: Optional[OrganizationStatus] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


class OrganizationRef(SchemaModel):
    uuid: str
    name: str


class OrganizationOutput(OrganizationBase):
    uuid: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
