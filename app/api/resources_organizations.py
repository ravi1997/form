"""Organization CRUD endpoints."""

from __future__ import annotations

from flask import g
from mongoengine.errors import NotUniqueError, ValidationError

from app.models.user import Organization, User, Invitation
from app.schemas.mappers import to_json_ready, to_organization_output
from app.schemas.organization import OrganizationCreateInput, OrganizationOutput, OrganizationUpdateInput
from app.api.resources_schemas import (
    AddAdminInput,
    AdminPath,
    ErrorResponse,
    ListQuery,
    MessageResponse,
    OrganizationAdminsResponse,
    OrganizationListResponse,
    UUIDPath,
    InvitationInput,
    InvitationOutput,
)
from app.api.resources_support import _error, resources_api, resources_tag
from app.api.resources_context import _resolve_refs, _resolve_user
from app.api.resources_utils import paginate_queryset_with_predicate
from app.utils import utcnow


@resources_api.post(
    "/organizations",
    tags=[resources_tag],
    responses={201: OrganizationOutput, 400: ErrorResponse},
)
def create_organization(body: OrganizationCreateInput):
    try:
        organization = Organization(
            uuid=body.uuid,
            name=body.name,
            admins=_resolve_refs(User, body.admins, "admin"),
            status=body.status,
        )
        organization.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_organization_output(organization)), 201


@resources_api.get(
    "/organizations",
    tags=[resources_tag],
    responses={200: OrganizationListResponse},
)
def list_organizations(query: ListQuery):
    qs = Organization.objects
    if query.status:
        qs = qs(status=query.status)
    try:
        items, page, page_size, total_items, total_pages, next_cursor = (
            paginate_queryset_with_predicate(
                qs,
                query,
                lambda org: True,
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        OrganizationListResponse(
            items=[to_organization_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/organizations/<uuid>",
    tags=[resources_tag],
    responses={200: OrganizationOutput, 404: ErrorResponse},
)
def get_organization(path: UUIDPath):
    item = Organization.objects(uuid=path.uuid).first()
    if not item:
        return _error("Organization not found", 404)
    return to_json_ready(to_organization_output(item))


@resources_api.patch(
    "/organizations/<uuid>",
    tags=[resources_tag],
    responses={200: OrganizationOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_organization(path: UUIDPath, body: OrganizationUpdateInput):
    item = Organization.objects(uuid=path.uuid).first()
    if not item:
        return _error("Organization not found", 404)
    try:
        if body.name is not None:
            item.name = body.name
        if body.admins is not None:
            item.admins = _resolve_refs(User, body.admins, "admin")
        if body.status is not None:
            item.status = body.status
        if body.deleted_at is not None:
            item.deleted_at = body.deleted_at
        if body.deleted_by is not None:
            item.deleted_by = _resolve_user(body.deleted_by)
        item.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_organization_output(item))


@resources_api.delete(
    "/organizations/<uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_organization(path: UUIDPath):
    item = Organization.objects(uuid=path.uuid).first()
    if not item:
        return _error("Organization not found", 404)
    user = getattr(g, "resources_user", None)
    item.status = "deleted"
    item.deleted_at = utcnow()
    if user:
        item.deleted_by = user
    item.save()
    return to_json_ready(MessageResponse(message="organization_deleted"))


@resources_api.get(
    "/organizations/<uuid>/admins",
    tags=[resources_tag],
    responses={200: OrganizationAdminsResponse, 404: ErrorResponse},
)
def get_organization_admins(path: UUIDPath):
    item = Organization.objects(uuid=path.uuid).first()
    if not item:
        return _error("Organization not found", 404)
    
    from app.schemas.mappers import to_user_output
    admins_output = [to_user_output(admin) for admin in item.admins or []]
    return to_json_ready(OrganizationAdminsResponse(admins=admins_output))


@resources_api.post(
    "/organizations/<uuid>/admins",
    tags=[resources_tag],
    responses={200: OrganizationAdminsResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def add_organization_admin(path: UUIDPath, body: AddAdminInput):
    organization = Organization.objects(uuid=path.uuid).first()
    if not organization:
        return _error("Organization not found", 404)
    
    user = User.objects(uuid=body.user_uuid).first()
    if not user:
        return _error("User not found", 404)
    
    try:
        # Add user to organization admins list
        if user not in organization.admins:
            organization.admins.append(user)
            organization.save()
        
        # Add organization to user organizations list
        if organization not in user.organizations:
            user.organizations.append(organization)
        
        # Add admin role for this organization
        org_id_str = str(organization.id)
        if org_id_str not in user.roles:
            user.roles[org_id_str] = []
        if "admin" not in user.roles[org_id_str]:
            user.roles[org_id_str].append("admin")
            
        user.is_organisation_admin = True
        user.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
        
    from app.schemas.mappers import to_user_output
    admins_output = [to_user_output(admin) for admin in organization.admins or []]
    return to_json_ready(OrganizationAdminsResponse(admins=admins_output))


@resources_api.delete(
    "/organizations/<uuid>/admins/<user_uuid>",
    tags=[resources_tag],
    responses={200: OrganizationAdminsResponse, 400: ErrorResponse, 404: ErrorResponse},
)
def remove_organization_admin(path: AdminPath):
    organization = Organization.objects(uuid=path.uuid).first()
    if not organization:
        return _error("Organization not found", 404)
    
    user = User.objects(uuid=path.user_uuid).first()
    if not user:
        return _error("User not found", 404)
    
    try:
        # Remove user from organization admins list
        if user in organization.admins:
            organization.admins.remove(user)
            organization.save()
        
        # Remove admin role for this organization
        org_id_str = str(organization.id)
        if org_id_str in user.roles:
            if "admin" in user.roles[org_id_str]:
                user.roles[org_id_str].remove("admin")
            if not user.roles[org_id_str]:
                del user.roles[org_id_str]
        
        # Check if they have any other admin roles in any organization
        has_other_admin_role = any("admin" in roles for roles in (user.roles or {}).values())
        if not has_other_admin_role:
            user.is_organisation_admin = False
            
        user.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
        
    from app.schemas.mappers import to_user_output
    admins_output = [to_user_output(admin) for admin in organization.admins or []]
    return to_json_ready(OrganizationAdminsResponse(admins=admins_output))


from uuid import uuid4
from datetime import timedelta

@resources_api.post(
    "/organizations/<uuid>/invitations",
    tags=[resources_tag],
    responses={201: InvitationOutput, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def create_organization_invitation(path: UUIDPath, body: InvitationInput):
    org = Organization.objects(uuid=path.uuid).first()
    if not org:
        return _error("Organization not found", 404)

    user = getattr(g, "resources_user", None)
    if not user:
        return _error("Unauthorized", 401)

    # Check permission: creator must be either superadmin or admin of this organization
    is_admin = False
    if user.is_super_admin:
        is_admin = True
    elif user in org.admins:
        is_admin = True
    else:
        org_id_str = str(org.id)
        if org_id_str in user.roles and "admin" in user.roles[org_id_str]:
            is_admin = True
        elif org.uuid in user.roles and "admin" in user.roles[org.uuid]:
            is_admin = True

    if not is_admin:
        return _error("Forbidden: You must be an administrator of this organization to send invitations", 403)

    # Enforce: only superadmin can invite someone as organization admin
    if body.role == "admin" and not user.is_super_admin:
        return _error("Forbidden: Only superadmins can invite organization administrators", 403)

    # Create Invitation
    now = utcnow()
    invitation = Invitation(
        uuid=str(uuid4()),
        organization=org,
        email=body.email.strip().lower(),
        phone=body.phone,
        role=body.role,
        status="pending",
        created_by=user,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    invitation.save()

    invitation_link = f"http://localhost:8600/api/v1/invitations/{invitation.uuid}/accept"

    output = InvitationOutput(
        uuid=invitation.uuid,
        organization_uuid=org.uuid,
        email=invitation.email,
        phone=invitation.phone,
        role=invitation.role,
        status=invitation.status,
        created_by_uuid=user.uuid,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        invitation_link=invitation_link,
    )
    return to_json_ready(output), 201


@resources_api.post(
    "/invitations/<uuid>/accept",
    tags=[resources_tag],
    responses={200: MessageResponse, 400: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse},
)
def accept_organization_invitation(path: UUIDPath):
    invitation = Invitation.objects(uuid=path.uuid).first()
    if not invitation:
        return _error("Invitation not found", 404)

    if invitation.status != "pending":
        return _error(f"Invitation is already {invitation.status}", 400)

    if invitation.expires_at < utcnow().replace(tzinfo=None):
        invitation.status = "expired"
        invitation.save()
        return _error("Invitation has expired", 400)

    user = getattr(g, "resources_user", None)
    if not user:
        return _error("Unauthorized", 401)

    # Check if the logged-in user matches the invitation's email (or phone if provided)
    email_matches = user.email.strip().lower() == invitation.email.strip().lower()
    phone_matches = False
    if invitation.phone and user.phone:
        phone_matches = user.phone.strip() == invitation.phone.strip()

    if not (email_matches or phone_matches):
        return _error("Forbidden: Your account does not match the invited email or phone number", 403)

    # Add user to organization
    org = invitation.organization
    if org not in user.organizations:
        user.organizations.append(org)

    # Assign role
    org_id_str = str(org.id)
    if not user.roles:
        user.roles = {}
    
    current_roles = user.roles.get(org_id_str) or []
    if invitation.role not in current_roles:
        current_roles.append(invitation.role)
        user.roles[org_id_str] = current_roles

    # If the role is admin, handle flags
    if invitation.role == "admin":
        user.is_organisation_admin = True
        if user not in org.admins:
            org.admins.append(user)
            org.save()

    user.save()

    invitation.status = "accepted"
    invitation.save()

    return to_json_ready(MessageResponse(message="invitation_accepted"))
