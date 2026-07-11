from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from app.schemas.action import ActionExecutionOutput
from app.schemas.choice import ChoiceOutput
from app.schemas.common import SchemaModel
from app.schemas.form import FormOutput
from app.schemas.organization import OrganizationOutput
from app.schemas.project import ProjectOutput
from app.schemas.user import UserOutput
from app.schemas.question import QuestionOutput
from app.schemas.section import SectionOutput


class MessageResponse(SchemaModel):
    message: str


class ErrorResponse(SchemaModel):
    message: str


class UUIDPath(SchemaModel):
    uuid: str


class VersionPath(SchemaModel):
    uuid: str
    version_uuid: str


class ProjectPath(SchemaModel):
    project_uuid: str


class FormPath(SchemaModel):
    project_uuid: str
    form_uuid: str


class SectionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str


class QuestionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str


class QuestionActionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    action_id: str


class ResponseActionExecutionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    response_uuid: str


class FormVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    version_uuid: str


class SectionVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    version_uuid: str


class QuestionVersionPath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    version_uuid: str


class ChoicePath(SchemaModel):
    project_uuid: str
    form_uuid: str
    section_uuid: str
    question_uuid: str
    choice_uuid: str


class ConditionPath(SchemaModel):
    condition_uuid: str


class ConditionVersionDiffQuery(SchemaModel):
    from_version: str
    to_version: str


class ConditionRollbackRequest(SchemaModel):
    version_id: str


class ConditionBatchTestItem(SchemaModel):
    condition_uuid: str
    test_context: Dict[str, Any]
    enable_tracing: bool = False


class ConditionBatchTestRequest(SchemaModel):
    items: List[ConditionBatchTestItem]


class ConditionImportRequest(SchemaModel):
    conditions: List[Dict[str, Any]]
    overwrite: bool = False


class AsyncEvaluationRequest(SchemaModel):
    condition_uuid: str
    context: Dict[str, Any]
    timeout_seconds: float = 2.0


class VersionLinkQuery(SchemaModel):
    version_uuid: Optional[str] = None


class ListQuery(SchemaModel):
    status: Optional[str] = None
    cursor: Optional[str] = None
    page: int = 1
    page_size: int = 20
    limit: Optional[int] = None
    offset: Optional[int] = None


class ProjectListResponse(SchemaModel):
    items: List[ProjectOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class FormListResponse(SchemaModel):
    items: List[FormOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class SectionListResponse(SchemaModel):
    items: List[SectionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class QuestionListResponse(SchemaModel):
    items: List[QuestionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class ChoiceListResponse(SchemaModel):
    items: List[ChoiceOutput]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    next_cursor: Optional[str] = None


class WorkflowActionRequest(SchemaModel):
    note: Optional[str] = None


class WorkflowActionResponse(SchemaModel):
    message: str
    action: Literal["submit", "review", "approve"]
    actor_user_uuid: str
    form_uuid: str
    project_uuid: str


class ActionExecutionListResponse(SchemaModel):
    items: List[ActionExecutionOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class OrganizationListResponse(SchemaModel):
    items: List[OrganizationOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None
    next_cursor: Optional[str] = None


class AddAdminInput(SchemaModel):
    user_uuid: str


class AdminPath(SchemaModel):
    uuid: str
    user_uuid: str


class OrganizationAdminsResponse(SchemaModel):
    admins: List[UserOutput]


class UserListResponse(SchemaModel):
    items: List[UserOutput]
    page: int
    page_size: int
    total_items: Optional[int] = None
    total_pages: Optional[int] = None


from datetime import datetime
from pydantic import EmailStr

class InvitationInput(SchemaModel):
    email: EmailStr
    phone: Optional[str] = None
    role: str = "viewer"


class InvitationOutput(SchemaModel):
    uuid: str
    organization_uuid: str
    email: str
    phone: Optional[str] = None
    role: str
    status: str
    created_by_uuid: str
    created_at: datetime
    expires_at: datetime
    invitation_link: str
