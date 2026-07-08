from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum


class RateLimitUnitEnum(str, Enum):
    second = "second"
    minute = "minute"
    hour = "hour"
    day = "day"


class RateLimitScopeEnum(str, Enum):
    global_scope = "global"
    user = "user"
    route = "route"
    organization = "organization"


class RateLimitCreateRequest(BaseModel):
    """Request body for creating a new rate limit rule."""

    rule_id: str = Field(..., description="Unique identifier for the rule")
    scope: RateLimitScopeEnum = Field(..., description="Scope of the rate limit")
    target_id: Optional[str] = Field(
        None, description="Target UUID (user/org) or route path"
    )
    max_requests: int = Field(..., ge=1, description="Maximum requests allowed")
    window_size: int = Field(..., ge=1, description="Time window size")
    unit: RateLimitUnitEnum = Field(default="minute", description="Time unit")
    http_method: Optional[str] = Field(
        None, description="HTTP method (GET, POST, etc.)"
    )
    route_pattern: Optional[str] = Field(None, description="Route pattern")
    description: Optional[str] = Field(None, description="Description of the rule")
    is_active: bool = Field(default=True, description="Is the rule active?")
    priority: int = Field(default=0, description="Priority level")

    @field_validator("http_method")
    @classmethod
    def validate_http_method(cls, v):
        if v:
            valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
            if v.upper() not in valid_methods:
                raise ValueError(f"Invalid HTTP method. Must be one of {valid_methods}")
        return v


class RateLimitUpdateRequest(BaseModel):
    """Request body for updating a rate limit rule."""

    max_requests: Optional[int] = Field(
        None, ge=1, description="Maximum requests allowed"
    )
    window_size: Optional[int] = Field(None, ge=1, description="Time window size")
    unit: Optional[RateLimitUnitEnum] = Field(None, description="Time unit")
    http_method: Optional[str] = Field(None, description="HTTP method")
    description: Optional[str] = Field(None, description="Description of the rule")
    is_active: Optional[bool] = Field(None, description="Is the rule active?")
    priority: Optional[int] = Field(None, description="Priority level")


class RateLimitResponse(BaseModel):
    """Response model for rate limit rules."""

    rule_id: str
    scope: str
    target_id: Optional[str]
    max_requests: int
    window_size: int
    unit: str
    http_method: Optional[str]
    route_pattern: Optional[str]
    description: Optional[str]
    is_active: bool
    priority: int
    created_at: Optional[str]
    updated_at: Optional[str]


class RateLimitListResponse(BaseModel):
    """Response model for listing rate limits."""

    total: int
    limits: List[RateLimitResponse]
    filters: Optional[dict] = None


class RateLimitLogResponse(BaseModel):
    """Response model for rate limit logs."""

    user_id: Optional[str]
    organization_id: Optional[str]
    route_pattern: str
    http_method: str
    ip_address: Optional[str]
    rule_id: str
    blocked: bool
    request_count: int
    max_allowed: int
    timestamp: str


class RateLimitLogsListResponse(BaseModel):
    """Response model for listing rate limit logs."""

    total: int
    logs: List[RateLimitLogResponse]
    filters: Optional[dict] = None


class RateLimitResetRequest(BaseModel):
    """Request body for resetting a rate limit counter."""

    scope: str = Field(..., description="Scope (global, user, route, organization)")
    target: Optional[str] = Field(None, description="Target ID")
    route: str = Field(..., description="Route pattern")
    method: Optional[str] = Field(None, description="HTTP method")


class RateLimitResetResponse(BaseModel):
    """Response model for reset operation."""

    success: bool
    message: str


class RateLimitStatusResponse(BaseModel):
    """Response model for rate limit status."""

    limits: List[RateLimitResponse]
    total: int


class BulkRateLimitUpdateRequest(BaseModel):
    """Request body for bulk updating rate limits."""

    rule_ids: List[str] = Field(..., description="List of rule IDs to update")
    updates: RateLimitUpdateRequest = Field(
        ..., description="Updates to apply to all rules"
    )


class RateLimitDeleteResponse(BaseModel):
    """Response model for delete operation."""

    message: str


class BulkRateLimitUpdateResponse(BaseModel):
    """Response model for bulk update."""

    updated_count: int
    failed_count: int
    message: str
