from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from app.schemas.common import SchemaModel
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput

DocumentStatus = Literal["active", "inactive", "deleted"]


class ProjectBase(SchemaModel):
    name: str
    admins: List[str] = Field(default_factory=list)
    members: List[str] = Field(default_factory=list)
    viewers: List[str] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    status: DocumentStatus = "active"


class ProjectCreateInput(ProjectBase):
    uuid: str
    versions: List[VersionCreateInput] = Field(default_factory=list)


class ProjectUpdateInput(SchemaModel):
    name: Optional[str] = None
    versions: Optional[List[VersionUpdateInput]] = None
    admins: Optional[List[str]] = None
    members: Optional[List[str]] = None
    viewers: Optional[List[str]] = None
    forms: Optional[List[str]] = None
    organizations: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[DocumentStatus] = None


class ProjectRef(SchemaModel):
    uuid: str
    name: str


class ProjectOutput(ProjectBase):
    uuid: str
    versions: List[VersionOutput] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
