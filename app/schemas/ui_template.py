from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from app.schemas.common import SchemaModel

TemplateScopeType = Literal["global", "organization", "project"]
TemplateVisibility = Literal["private", "shared", "public"]
TemplateStatus = Literal["draft", "published", "archived", "deprecated"]
TemplateRevisionStatus = Literal["draft", "published", "archived"]


class TemplateRevisionBase(SchemaModel):
    schema_version: int = Field(default=1, ge=1)
    config: Dict[str, Any] = Field(default_factory=dict)
    change_note: Optional[str] = None
    status: TemplateRevisionStatus = "draft"


class TemplateRevisionCreateInput(TemplateRevisionBase):
    uuid: str


class TemplateRevisionOutput(TemplateRevisionBase):
    uuid: str
    version: int = Field(ge=1)
    created_by: Optional[str] = None
    created_at: datetime


class UiTemplateBase(SchemaModel):
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    icon: Optional[str] = None
    scope_type: TemplateScopeType = "global"
    scope_uuid: Optional[str] = None
    visibility: TemplateVisibility = "private"
    admins: List[str] = Field(default_factory=list)
    editors: List[str] = Field(default_factory=list)
    viewers: List[str] = Field(default_factory=list)
    status: TemplateStatus = "draft"


class UiTemplateCreateInput(UiTemplateBase):
    uuid: str
    initial_revision: Optional[TemplateRevisionCreateInput] = None


class UiTemplateUpdateInput(SchemaModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    icon: Optional[str] = None
    scope_type: Optional[TemplateScopeType] = None
    scope_uuid: Optional[str] = None
    visibility: Optional[TemplateVisibility] = None
    admins: Optional[List[str]] = None
    editors: Optional[List[str]] = None
    viewers: Optional[List[str]] = None
    status: Optional[TemplateStatus] = None


class UiTemplateOutput(UiTemplateBase):
    uuid: str
    revisions: List[TemplateRevisionOutput] = Field(default_factory=list)
    current_revision_uuid: Optional[str] = None
    usage_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None


ThemeTemplateCreateInput = UiTemplateCreateInput
ThemeTemplateUpdateInput = UiTemplateUpdateInput
ThemeTemplateOutput = UiTemplateOutput
LayoutTemplateCreateInput = UiTemplateCreateInput
LayoutTemplateUpdateInput = UiTemplateUpdateInput
LayoutTemplateOutput = UiTemplateOutput


class ThemeTemplateListResponse(SchemaModel):
    items: List[ThemeTemplateOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class LayoutTemplateListResponse(SchemaModel):
    items: List[LayoutTemplateOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None



class TemplateBindInput(SchemaModel):
    template_uuid: str
    revision_uuid: Optional[str] = None


class UiOverridesUpdateInput(SchemaModel):
    ui_overrides: Dict[str, Any] = Field(default_factory=dict)


class EffectiveUiConfigOutput(SchemaModel):
    theme_template_uuid: Optional[str] = None
    theme_revision_uuid: Optional[str] = None
    layout_template_uuid: Optional[str] = None
    layout_revision_uuid: Optional[str] = None
    theme_config: Dict[str, Any] = Field(default_factory=dict)
    layout_config: Dict[str, Any] = Field(default_factory=dict)
    ui_overrides: Dict[str, Any] = Field(default_factory=dict)
    effective_ui_config: Dict[str, Any] = Field(default_factory=dict)
