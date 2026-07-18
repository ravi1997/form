from app.extensions import db
from app.services.condition_metadata import validate_condition_operator
from datetime import datetime, timezone
from mongoengine.errors import ValidationError

VERSION_STATUS_CHOICES = (
    "published",
    "archived",
    "deleted",
    "draft",
    "disabled",
)

CONDITION_TYPE_CHOICES = (
    "regex",
    "comparison",
    "logical",
    "temporal",
    "arithmetic",
    "set",
    "dsl",
    "custom",
)

DOCUMENT_STATUS_CHOICES = (
    "active",
    "inactive",
    "deleted",
)

FORM_WORKFLOW_STATE_CHOICES = (
    "draft",
    "submitted",
    "in_review",
    "approved",
    "rejected",
)

FORM_WORKFLOW_ALLOWED_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"in_review", "approved", "rejected"},
    "in_review": {"approved", "rejected"},
    "approved": set(),
    "rejected": {"submitted"},
}

FORM_RESPONSE_STATUS_CHOICES = (
    "draft",
    "submitted",
    "in_review",
    "approved",
    "rejected",
    "deleted",
)

FORM_RESPONSE_ALLOWED_TRANSITIONS = {
    "draft": {"submitted", "deleted"},
    "submitted": {"in_review", "rejected", "deleted"},
    "in_review": {"approved", "rejected", "deleted"},
    "approved": {"deleted"},
    "rejected": {"submitted", "deleted"},
}


def _collect_version_uuids(versions):
    uuids = []
    for version in versions or []:
        if version.uuid:
            uuids.append(version.uuid)
    return uuids


def _ensure_unique_values(values, field_name):
    if len(values) != len(set(values)):
        raise ValidationError(f"Duplicate values found in {field_name}")


def _unique_ref_count(ref_list):
    unique_ids = set()
    for ref in ref_list or []:
        if ref is None:
            continue
        ref_id = getattr(ref, "id", None)
        unique_ids.add(str(ref_id) if ref_id is not None else str(ref))
    return len(unique_ids)


def _validate_versioned_map_keys(versioned_map, versions, field_name):
    if not versioned_map:
        return

    valid_uuids = set(_collect_version_uuids(versions))
    invalid_keys = [key for key in versioned_map.keys() if key not in valid_uuids]

    if invalid_keys:
        raise ValidationError(
            f"{field_name} contains unknown version UUID keys: {', '.join(invalid_keys)}"
        )


def _persisted_state(instance, field_name):
    cache = getattr(instance, "_persisted_state_cache", None)
    if isinstance(cache, dict) and field_name in cache:
        return cache[field_name]

    if not getattr(instance, "id", None):
        return None

    persisted = instance.__class__.objects(id=instance.id).only(field_name).first()
    if not persisted:
        return None
    return getattr(persisted, field_name, None)


def _ensure_transition_allowed(previous_state, new_state, allowed_map, field_name):
    if previous_state is None or previous_state == new_state:
        return

    allowed = allowed_map.get(previous_state, set())
    if new_state not in allowed:
        raise ValidationError(
            f"Invalid {field_name} transition: {previous_state} -> {new_state}"
        )


class Version(db.EmbeddedDocument):
    uuid = db.StringField(required=True)

    major = db.IntField(required=True, min_value=0, default=0)
    minor = db.IntField(required=True, min_value=0, default=0)
    patch = db.IntField(required=True, min_value=0, default=0)

    created = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    created_by = db.ReferenceField("User")

    updated = db.DateTimeField()
    updated_by = db.ReferenceField("User")

    status = db.StringField(
        choices=VERSION_STATUS_CHOICES,
        default="draft",
    )

    def clean(self):
        if self.created and self.updated is None:
            self.updated = self.created


class Condition(db.Document):
    uuid = db.StringField(required=True, unique=True)

    conditionType = db.StringField(choices=CONDITION_TYPE_CHOICES)
    expression = db.StringField()

    targetField = db.StringField()
    sourceSectionUuid = db.StringField()

    operator = db.StringField()
    operands = db.ListField(db.DynamicField())

    isNegated = db.BooleanField(default=False)

    # recursive tree support
    subConditions = db.ListField(db.ReferenceField("self"))
    logicalJoinType = db.StringField(choices=["AND", "OR"])

    isActive = db.BooleanField(default=True)

    errorMessage = db.StringField()
    description = db.StringField()

    priority = db.IntField(default=0)
    stopEvaluationIfTrue = db.BooleanField(default=False)

    metadata = db.DictField()

    approval_state = db.StringField(
        choices=("draft", "review", "published", "deprecated", "archived"),
        default="draft",
    )
    published_at = db.DateTimeField()
    deprecated_at = db.DateTimeField()

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(choices=DOCUMENT_STATUS_CHOICES, default="active")

    meta = {
        "collection": "conditions",
        "indexes": [
            "uuid",
            "conditionType",
            "status",
            "priority",
            "updated_at",
            "approval_state",
            ("conditionType", "operator", "targetField"),
        ],
    }

    def clean(self):
        if not self.conditionType:
            raise ValidationError("conditionType is required")

        is_logical = self.conditionType == "logical"

        if is_logical:
            if not self.logicalJoinType:
                raise ValidationError(
                    "logicalJoinType is required for logical conditions"
                )
            if not self.subConditions:
                raise ValidationError(
                    "Logical conditions require at least one sub-condition"
                )
            if self.expression or self.operator or self.operands:
                raise ValidationError(
                    "Logical conditions cannot also define expression/operator/operands"
                )

            if self.id is not None:
                for sub_condition in self.subConditions:
                    if sub_condition.pk == self.id:
                        raise ValidationError(
                            "A condition cannot reference itself as sub-condition"
                        )
        else:
            if self.logicalJoinType:
                raise ValidationError(
                    "logicalJoinType is only valid for logical conditions"
                )
            if self.subConditions:
                raise ValidationError(
                    "subConditions are only valid for logical conditions"
                )

            if self.conditionType == "regex":
                if not self.expression or not self.targetField:
                    raise ValidationError(
                        "Regex conditions require expression and targetField"
                    )
                try:
                    validate_condition_operator(self.conditionType, self.operator)
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc

            if self.conditionType in ("comparison", "temporal", "set"):
                if not self.targetField or not self.operator:
                    raise ValidationError(
                        "Comparison conditions require targetField and operator"
                    )
                try:
                    validate_condition_operator(self.conditionType, self.operator)
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
                if (
                    self.operator not in ("is_empty", "is_not_empty")
                    and not self.operands
                ):
                    raise ValidationError(
                        "Comparison conditions require at least one operand"
                    )

            if (
                self.conditionType in ("custom", "dsl", "arithmetic")
                and not self.expression
            ):
                raise ValidationError("Custom conditions require expression")
            if self.conditionType in ("custom", "dsl", "arithmetic") and self.operator:
                try:
                    validate_condition_operator(self.conditionType, self.operator)
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc

    def save(self, *args, **kwargs):
        saving_ids = kwargs.pop("_saving_ids", None)
        if saving_ids is None:
            saving_ids = set()
        current_id = id(self)
        if current_id in saving_ids:
            self.updated_at = datetime.now(timezone.utc)
            return super().save(*args, **kwargs)

        saving_ids.add(current_id)

        unsaved_sub_conditions = [
            sub_condition
            for sub_condition in (self.subConditions or [])
            if getattr(sub_condition, "pk", None) is None
        ]
        if unsaved_sub_conditions:
            original_sub_conditions = list(self.subConditions or [])
            self.subConditions = []
            self.updated_at = datetime.now(timezone.utc)
            super().save(*args, validate=False, **kwargs)

            for sub_condition in unsaved_sub_conditions:
                if id(sub_condition) in saving_ids:
                    continue
                if getattr(sub_condition, "pk", None) is None:
                    sub_condition.save(_saving_ids=saving_ids)

            self.subConditions = original_sub_conditions

        self.updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        try:
            from app.services.condition_management_analysis import (
                invalidate_condition_usage_cache,
            )
            from app.services.condition_management_graph import (
                invalidate_dependency_graph_cache,
            )
            from app.services.condition_management_monitoring import (
                invalidate_monitoring_cache,
            )

            invalidate_dependency_graph_cache()
            invalidate_condition_usage_cache()
            invalidate_monitoring_cache()
        except Exception:
            pass
        return result


class Choice(db.EmbeddedDocument):
    uuid = db.StringField(required=True)
    label = db.StringField(required=True)
    value = db.StringField(required=True)

    visibility_condition = db.ReferenceField("Condition")


class FormWorkflowEvent(db.EmbeddedDocument):
    action = db.StringField(required=True, choices=("submit", "review", "approve"))
    actor_user_uuid = db.StringField(required=True)
    note = db.StringField()
    transition_from = db.StringField(choices=FORM_WORKFLOW_STATE_CHOICES)
    transition_to = db.StringField(choices=FORM_WORKFLOW_STATE_CHOICES)
    outcome = db.StringField(
        required=True, choices=("success", "idempotent", "rejected")
    )
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    request_id = db.StringField()


class FormResponseStatusEvent(db.EmbeddedDocument):
    transition_from = db.StringField(choices=FORM_RESPONSE_STATUS_CHOICES)
    transition_to = db.StringField(required=True, choices=FORM_RESPONSE_STATUS_CHOICES)
    changed_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    reason = db.StringField()


class ActionStep(db.EmbeddedDocument):
    id = db.StringField(required=True)
    target = db.StringField(required=True, choices=("frontend", "backend"))
    type = db.StringField(required=True)
    config = db.DictField(default=dict)
    on_error = db.StringField(default="stop", choices=("stop", "continue"))


class ActionDefinition(db.EmbeddedDocument):
    id = db.StringField(required=True)
    label = db.StringField(required=True)
    icon = db.StringField()
    button_variant = db.StringField()
    trigger = db.StringField(default="click")
    confirmation_message = db.StringField()
    schema_version = db.IntField(default=1, min_value=1)
    audit_policy = db.StringField(
        default="always", choices=("always", "backend_only", "never")
    )
    allowed_roles = db.ListField(db.StringField(), default=list)
    visibility_condition = db.ReferenceField("Condition")
    enabled_condition = db.ReferenceField("Condition")
    metadata = db.DictField(default=dict)
    steps = db.ListField(db.EmbeddedDocumentField(ActionStep), default=list)

    def clean(self):
        if not self.steps:
            raise ValidationError("Action definitions require at least one step")
        step_ids = [step.id for step in self.steps if step.id]
        _ensure_unique_values(step_ids, "ActionDefinition.steps.id")


class Question(db.Document):
    uuid = db.StringField(required=True, unique=True)

    versions = db.ListField(db.EmbeddedDocumentField(Version))

    type = db.StringField(required=True)

    label = db.StringField(required=True)
    placeholder = db.StringField()
    description = db.StringField()
    default_value = db.DynamicField()
    help_text = db.StringField()
    tooltip = db.StringField()

    validation_conditions = db.ListField(db.ReferenceField("Condition"))
    validation_condition_messages = db.MapField(db.StringField())

    visibility_conditions = db.ListField(db.ReferenceField("Condition"))

    add_button = db.BooleanField(default=False)

    is_repeatable = db.BooleanField(default=False)
    repeatable_condition = db.ReferenceField("Condition")

    check_repeat_on = db.StringField()

    min_repeatable_count = db.IntField()
    max_repeatable_count = db.IntField()

    isAction = db.BooleanField(default=False)
    actionButtonType = db.StringField()
    actionType = db.StringField()
    actionLabel = db.StringField()
    actions = db.ListField(db.EmbeddedDocumentField(ActionDefinition), default=list)

    tags = db.ListField(db.StringField())

    choices = db.ListField(db.EmbeddedDocumentField(Choice))

    hideButton = db.BooleanField(default=False)

    actionIcon = db.StringField()

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(choices=DOCUMENT_STATUS_CHOICES, default="active")

    meta = {
        "collection": "questions",
        "indexes": ["uuid", "type", "status", "tags"],
    }

    def clean(self):
        _ensure_unique_values(
            _collect_version_uuids(self.versions), "Question.versions.uuid"
        )

        if (
            self.min_repeatable_count is not None
            and self.max_repeatable_count is not None
            and self.min_repeatable_count > self.max_repeatable_count
        ):
            raise ValidationError(
                "min_repeatable_count cannot be greater than max_repeatable_count"
            )

        if self.is_repeatable:
            if self.min_repeatable_count is None:
                self.min_repeatable_count = 1
            if self.max_repeatable_count is None:
                self.max_repeatable_count = 10

        if self.isAction and (not self.actionType or not self.actionLabel):
            raise ValidationError("Action questions require actionType and actionLabel")

        if self.actions:
            action_ids = [action.id for action in self.actions if action.id]
            _ensure_unique_values(action_ids, "Question.actions.id")
            self.isAction = True
            first_action = self.actions[0]
            if not self.actionLabel:
                self.actionLabel = first_action.label
            if not self.actionType and first_action.steps:
                self.actionType = first_action.steps[0].type

        if self.choices:
            choice_uuids = [choice.uuid for choice in self.choices]
            choice_values = [choice.value for choice in self.choices]
            _ensure_unique_values(choice_uuids, "Question.choices.uuid")
            _ensure_unique_values(choice_values, "Question.choices.value")

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        self._persisted_state_cache = {"status": self.status}
        return result


class Section(db.Document):
    uuid = db.StringField(required=True, unique=True)

    versions = db.ListField(db.EmbeddedDocumentField(Version))

    # replaces Map<Version, Vector<Question>>
    questions = db.MapField(db.ListField(db.StringField()))
    # structure:
    # {
    #   "version_uuid": ["question_id1", "question_id2"]
    # }

    add_button = db.BooleanField(default=False)
    is_repeatable = db.BooleanField(default=False)

    repeatable_condition = db.ReferenceField("Condition")

    check_repeat_on = db.StringField()

    min_repeatable_count = db.IntField()
    max_repeatable_count = db.IntField()

    title = db.StringField()
    description = db.StringField()

    isDeleted = db.BooleanField(default=False)
    deletedBy = db.ReferenceField("User")
    deletedAt = db.DateTimeField()
    deleted_at = db.DateTimeField()
    deleted_by = db.ReferenceField("User")

    visibility_condition = db.ReferenceField("Condition")

    validation_conditions = db.ListField(db.ReferenceField("Condition"))
    validation_condition_messages = db.MapField(db.StringField())

    tags = db.ListField(db.StringField())
    icon = db.StringField()

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(choices=DOCUMENT_STATUS_CHOICES, default="active")

    meta = {
        "collection": "sections",
        "indexes": ["uuid", "status", "tags"],
    }

    def clean(self):
        _ensure_unique_values(
            _collect_version_uuids(self.versions), "Section.versions.uuid"
        )
        _validate_versioned_map_keys(self.questions, self.versions, "Section.questions")

        if (
            self.min_repeatable_count is not None
            and self.max_repeatable_count is not None
            and self.min_repeatable_count > self.max_repeatable_count
        ):
            raise ValidationError(
                "min_repeatable_count cannot be greater than max_repeatable_count"
            )

        if self.isDeleted:
            if not self.deletedAt:
                self.deletedAt = datetime.now(timezone.utc)
            if not self.deleted_at:
                self.deleted_at = self.deletedAt
        elif self.deleted_at and not self.deletedAt:
            self.deletedAt = self.deleted_at

        if self.deleted_by and not self.deletedBy:
            self.deletedBy = self.deleted_by
        elif self.deletedBy and not self.deleted_by:
            self.deleted_by = self.deletedBy

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        self._persisted_state_cache = {"status": self.status}
        return result


class Form(db.Document):
    uuid = db.StringField(required=True, unique=True)

    versions = db.ListField(db.EmbeddedDocumentField(Version))

    # Map<Version, Vector<Section>>
    sections = db.MapField(db.ListField(db.StringField()))

    editors = db.ListField(db.ReferenceField("User"))
    viewers = db.ListField(db.ReferenceField("User"))
    reviewers = db.ListField(db.ReferenceField("User"))
    approvers = db.ListField(db.ReferenceField("User"))
    submitters = db.ListField(db.ReferenceField("User"))

    requires_reviewer = db.BooleanField(default=False)
    requires_approver = db.BooleanField(default=False)
    min_reviewers_required = db.IntField(min_value=0, default=0)
    min_approvers_required = db.IntField(min_value=0, default=0)

    validation_conditions = db.ListField(db.ReferenceField("Condition"))
    validation_condition_messages = db.MapField(db.StringField())

    child_sections = db.ListField(db.ReferenceField("Section"))

    tags = db.ListField(db.StringField())
    icon = db.StringField()
    theme_template_uuid = db.StringField()
    theme_revision_uuid = db.StringField()
    layout_template_uuid = db.StringField()
    layout_revision_uuid = db.StringField()
    ui_overrides = db.DictField(default=dict)
    is_public = db.BooleanField(default=False)

    workflow_state = db.StringField(
        choices=FORM_WORKFLOW_STATE_CHOICES, default="draft"
    )
    workflow_updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    workflow_history = db.ListField(
        db.EmbeddedDocumentField(FormWorkflowEvent), default=list
    )

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(choices=DOCUMENT_STATUS_CHOICES, default="active")

    meta = {
        "collection": "forms",
        "indexes": [
            "uuid",
            "status",
            "tags",
            "theme_template_uuid",
            "layout_template_uuid",
        ],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._persisted_state_cache = {"workflow_state": self.workflow_state}

    def clean(self):
        previous_state = _persisted_state(self, "workflow_state")
        _ensure_transition_allowed(
            previous_state,
            self.workflow_state,
            FORM_WORKFLOW_ALLOWED_TRANSITIONS,
            "workflow_state",
        )

        _ensure_unique_values(
            _collect_version_uuids(self.versions), "Form.versions.uuid"
        )
        _validate_versioned_map_keys(self.sections, self.versions, "Form.sections")

        if self.min_reviewers_required > 0:
            self.requires_reviewer = True

        if self.min_approvers_required > 0:
            self.requires_approver = True

        if self.requires_reviewer and not self.reviewers:
            raise ValidationError("Form requires reviewers but reviewers list is empty")

        if self.requires_approver and not self.approvers:
            raise ValidationError("Form requires approvers but approvers list is empty")

        if self.requires_reviewer:
            required_reviewer_count = max(1, self.min_reviewers_required)
            if _unique_ref_count(self.reviewers) < required_reviewer_count:
                raise ValidationError(
                    f"Form requires at least {required_reviewer_count} unique reviewer(s)"
                )

        if self.requires_approver:
            required_approver_count = max(1, self.min_approvers_required)
            if _unique_ref_count(self.approvers) < required_approver_count:
                raise ValidationError(
                    f"Form requires at least {required_approver_count} unique approver(s)"
                )

        if self.workflow_state == "approved" and self.requires_reviewer:
            if self.min_reviewers_required > 0 and not self.reviewers:
                raise ValidationError("approved workflow requires reviewer assignments")

        if self.workflow_state == "approved" and self.requires_approver:
            if self.min_approvers_required > 0 and not self.approvers:
                raise ValidationError("approved workflow requires approver assignments")

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        self.workflow_updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        self._persisted_state_cache = {"workflow_state": self.workflow_state}
        return result


class Project(db.Document):
    uuid = db.StringField(required=True, unique=True)
    name = db.StringField(required=True)

    versions = db.ListField(db.EmbeddedDocumentField(Version))

    admins = db.ListField(db.ReferenceField("User"))
    members = db.ListField(db.ReferenceField("User"))
    viewers = db.ListField(db.ReferenceField("User"))

    forms = db.ListField(db.ReferenceField("Form"))

    organizations = db.ListField(db.ReferenceField("Organization"))

    tags = db.ListField(db.StringField())

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(choices=DOCUMENT_STATUS_CHOICES, default="active")

    meta = {
        "collection": "projects",
        "indexes": ["uuid", "name", "status", "tags"],
    }

    def clean(self):
        _ensure_unique_values(
            _collect_version_uuids(self.versions), "Project.versions.uuid"
        )

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        self._persisted_state_cache = {"status": self.status}
        return result


class ResponseItem(db.EmbeddedDocument):
    question_uuid = db.StringField(required=True)
    section_uuid = db.StringField()
    repeat_index = db.IntField(min_value=0)
    value = db.DynamicField()
    value_type = db.StringField()
    metadata = db.DictField()

    approval_state = db.StringField(
        choices=("draft", "review", "published", "deprecated", "archived"),
        default="draft",
    )
    published_at = db.DateTimeField()
    deprecated_at = db.DateTimeField()


class FormResponse(db.Document):
    uuid = db.StringField(required=True, unique=True)

    form = db.ReferenceField("Form", required=True)
    form_uuid = db.StringField(required=True)
    form_version_uuid = db.StringField(required=True)

    project = db.ReferenceField("Project")
    project_uuid = db.StringField()

    organization = db.ReferenceField("Organization")
    organization_uuid = db.StringField()

    submitted_by = db.ReferenceField("User")
    submitted_by_uuid = db.StringField()

    status = db.StringField(choices=FORM_RESPONSE_STATUS_CHOICES, default="draft")
    status_history = db.ListField(
        db.EmbeddedDocumentField(FormResponseStatusEvent), default=list
    )

    responses = db.ListField(db.EmbeddedDocumentField(ResponseItem), default=list)
    response_map = db.MapField(db.DynamicField(), default=dict)

    score = db.FloatField()
    validation_errors = db.MapField(db.StringField(), default=dict)

    submitted_at = db.DateTimeField()
    reviewed_at = db.DateTimeField()
    reviewed_by = db.ListField(db.ReferenceField("User"), default=list)
    approved_at = db.DateTimeField()
    approved_by = db.ListField(db.ReferenceField("User"), default=list)

    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    deleted_at = db.DateTimeField()
    deleted_by = db.ReferenceField("User")

    metadata = db.DictField()

    approval_state = db.StringField(
        choices=("draft", "review", "published", "deprecated", "archived"),
        default="draft",
    )
    published_at = db.DateTimeField()
    deprecated_at = db.DateTimeField()

    meta = {
        "collection": "form_responses",
        "indexes": [
            "uuid",
            "form",
            "form_uuid",
            "form_version_uuid",
            "status",
            "submitted_by",
            "reviewed_by",
            "approved_by",
            "organization",
            "project",
            "created_at",
            "updated_at",
        ],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._persisted_state_cache = {"status": self.status}

    def clean(self):
        previous_status = _persisted_state(self, "status")
        if self.status_history:
            last_transition = self.status_history[-1]
            history_status = getattr(last_transition, "transition_to", None)
            if (
                previous_status is not None
                and history_status is not None
                and previous_status != history_status
            ):
                previous_status = history_status
        _ensure_transition_allowed(
            previous_status,
            self.status,
            FORM_RESPONSE_ALLOWED_TRANSITIONS,
            "status",
        )

        if self.form and not self.form_uuid:
            self.form_uuid = self.form.uuid

        if self.project and not self.project_uuid:
            self.project_uuid = self.project.uuid

        if self.organization and not self.organization_uuid:
            self.organization_uuid = self.organization.uuid

        if self.submitted_by and not self.submitted_by_uuid:
            self.submitted_by_uuid = self.submitted_by.uuid

        if (
            self.status in ("submitted", "in_review", "approved", "rejected")
            and not self.submitted_at
        ):
            self.submitted_at = datetime.now(timezone.utc)

        requires_reviewer = bool(self.form and self.form.requires_reviewer)
        requires_approver = bool(self.form and self.form.requires_approver)
        min_reviewers_required = self.form.min_reviewers_required if self.form else 0
        min_approvers_required = self.form.min_approvers_required if self.form else 0

        required_reviewers = max(1, min_reviewers_required) if requires_reviewer else 0
        required_approvers = max(1, min_approvers_required) if requires_approver else 0

        if (
            required_reviewers > 0
            and self.status in ("in_review", "rejected", "approved")
            and _unique_ref_count(self.reviewed_by) < required_reviewers
        ):
            raise ValidationError(
                f"This form requires at least {required_reviewers} reviewer(s) before review outcome states"
            )

        if (
            required_approvers > 0
            and self.status == "approved"
            and _unique_ref_count(self.approved_by) < required_approvers
        ):
            raise ValidationError(
                f"This form requires at least {required_approvers} approver(s) before approval"
            )

        if (
            self.status in ("in_review", "approved", "rejected")
            and not self.reviewed_at
        ):
            self.reviewed_at = datetime.now(timezone.utc)
        if self.status in ("draft", "submitted"):
            self.reviewed_at = None
            self.reviewed_by = []

        if self.status == "approved" and not self.approved_at:
            self.approved_at = datetime.now(timezone.utc)
        if self.status in ("draft", "submitted", "in_review", "rejected"):
            self.approved_at = None
            self.approved_by = []

        if self.status == "deleted" and not self.deleted_at:
            self.deleted_at = datetime.now(timezone.utc)

        if self.status != "deleted":
            self.deleted_at = None
            self.deleted_by = None

        response_keys = []
        for item in self.responses:
            if item.question_uuid:
                response_keys.append(f"{item.question_uuid}:{item.repeat_index or 0}")

        _ensure_unique_values(
            response_keys, "FormResponse.responses.question_uuid+repeat_index"
        )

        if previous_status != self.status:
            self.status_history = list(self.status_history or [])
            self.status_history.append(
                FormResponseStatusEvent(
                    transition_from=previous_status,
                    transition_to=self.status,
                )
            )
        elif not self.status_history:
            self.status_history = [
                FormResponseStatusEvent(
                    transition_from=None,
                    transition_to=self.status,
                )
            ]

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        result = super().save(*args, **kwargs)
        self._persisted_state_cache = {"status": self.status}
        return result


class ActionExecution(db.Document):
    uuid = db.StringField(required=True, unique=True)
    project_uuid = db.StringField(required=True)
    form_uuid = db.StringField(required=True)
    section_uuid = db.StringField(required=True)
    question_uuid = db.StringField(required=True)
    action_id = db.StringField(required=True)
    response_uuid = db.StringField()
    actor_user_uuid = db.StringField(required=True)
    idempotency_key = db.StringField()
    status = db.StringField(
        required=True,
        choices=("pending", "success", "partial", "failed", "rejected", "idempotent"),
        default="pending",
    )
    frontend_steps = db.ListField(db.DictField(), default=list)
    step_results = db.ListField(db.DictField(), default=list)
    request_context = db.DictField(default=dict)
    client_state = db.DictField(default=dict)
    output = db.DictField(default=dict)
    error = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    completed_at = db.DateTimeField()
    request_id = db.StringField()

    meta = {
        "collection": "action_executions",
        "indexes": [
            "uuid",
            "project_uuid",
            "form_uuid",
            "response_uuid",
            "question_uuid",
            "action_id",
            "idempotency_key",
            "updated_at",
        ],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class ResponseAuditLog(db.Document):
    uuid = db.StringField(required=True, unique=True)
    response_uuid = db.StringField(required=True)
    actor_user_uuid = db.StringField()
    action = db.StringField(
        required=True,
        choices=("create", "update", "delete", "review", "approve", "reject"),
    )
    changes = db.DictField()
    timestamp = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "response_audit_logs",
        "indexes": [
            "uuid",
            "response_uuid",
            "actor_user_uuid",
            "timestamp",
        ],
    }
