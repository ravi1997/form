from __future__ import annotations

from flask import request, jsonify, g
from flask_openapi3 import APIBlueprint

from app.models.rate_limit import RateLimitConfig, RateLimitLog
from app.services.rate_limit import get_rate_limit_service
from app.schemas.auth import ErrorResponse
from app.schemas.rate_limit import (
    RateLimitCreateRequest,
    RateLimitUpdateRequest,
    RateLimitResponse,
    RateLimitListResponse,
    RateLimitLogsListResponse,
    RateLimitResetRequest,
    RateLimitResetResponse,
    RateLimitStatusResponse,
    BulkRateLimitUpdateRequest,
    BulkRateLimitUpdateResponse,
    RateLimitDeleteResponse,
)
from app.services.rbac import (
    resolve_access_identity_from_header,
    require_global_admin_by_payload,
)
from app.services import get_rotating_logger

logger = get_rotating_logger()


def _require_super_admin():
    """Check if current user is super admin."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None, jsonify({"error": "Authorization header missing"}), 401

    try:
        payload = resolve_access_identity_from_header(auth_header)
        user = require_global_admin_by_payload(payload)
        g.user = user
        g.user_id = payload.get("user_id")
        return user, None, None
    except Exception as e:
        logger.log_error("Authentication error", exception=e, context={"error": str(e)})
        return None, jsonify({"error": "Unauthorized"}), 401


def create_rate_limit_api(app) -> APIBlueprint:
    """Create rate limit management API endpoints."""

    api = APIBlueprint(
        "rate_limit",
        __name__,
        url_prefix="/api/v1/admin/rate-limits",
    )

    @api.before_request
    def _log_rate_limit_entry():
        logger.log_app_event(
            "API Started",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "request_id": getattr(g, "request_id", None),
                "user_id": getattr(g, "user_id", None),
            },
        )

    @api.after_request
    def _log_rate_limit_response(response):
        logger.log_app_event(
            "API Completed",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "status_code": response.status_code,
                "request_id": getattr(g, "request_id", None),
                "user_id": getattr(g, "user_id", None),
            },
        )
        return response

    # ==================== RATE LIMIT CONFIG ENDPOINTS ====================

    @api.post("/configs", responses={"201": RateLimitResponse, 401: ErrorResponse})
    def create_rate_limit_config():
        """
        Create a new rate limit configuration.
        Only super admin can access this.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            body = request.get_json()
            req = RateLimitCreateRequest(**body)

            # Check if rule_id already exists
            existing = RateLimitConfig.objects(rule_id=req.rule_id).first()
            if existing:
                return jsonify(
                    {"error": f"Rule with ID '{req.rule_id}' already exists"}
                ), 400

            # Create new config
            config = RateLimitConfig(
                rule_id=req.rule_id,
                scope=req.scope.value,
                target_id=req.target_id,
                max_requests=req.max_requests,
                window_size=req.window_size,
                unit=req.unit.value,
                http_method=req.http_method,
                route_pattern=req.route_pattern,
                description=req.description,
                is_active=req.is_active,
                priority=req.priority,
                created_by=g.user,
                updated_by=g.user,
            )
            config.clean()
            config.save()

            logger.log_app_event(
                f"Rate limit config created: {req.rule_id} by {g.user_id}",
                context={"rule_id": req.rule_id, "user_id": g.user_id},
            )

            return jsonify(config.to_dict()), 201

        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.log_error(
                "Error creating rate limit config",
                exception=e,
                context={"error": str(e), "rule_id": getattr(req, "rule_id", None)},
            )
            return jsonify({"error": "Failed to create rate limit config"}), 500

    @api.get("/configs", responses={"200": RateLimitListResponse, 401: ErrorResponse})
    def list_rate_limit_configs():
        """
        List all rate limit configurations.
        Supports filtering by scope, target_id, route_pattern, and active status.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            query = RateLimitConfig.objects()
            filters = {}

            # Apply filters from query parameters
            scope = request.args.get("scope")
            if scope:
                query = query.filter(scope=scope)
                filters["scope"] = scope

            target_id = request.args.get("target_id")
            if target_id:
                query = query.filter(target_id=target_id)
                filters["target_id"] = target_id

            route_pattern = request.args.get("route_pattern")
            if route_pattern:
                query = query.filter(route_pattern=route_pattern)
                filters["route_pattern"] = route_pattern

            is_active = request.args.get("is_active")
            if is_active is not None:
                is_active_bool = is_active.lower() in ("true", "1", "yes")
                query = query.filter(is_active=is_active_bool)
                filters["is_active"] = is_active_bool

            # Pagination
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 50))

            total = query.count()
            configs = (
                query.skip((page - 1) * per_page).limit(per_page).order_by("-priority")
            )

            return jsonify(
                {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "limits": [config.to_dict() for config in configs],
                    "filters": filters,
                }
            ), 200

        except Exception as e:
            logger.log_error(
                "Error listing rate limit configs",
                exception=e,
                context={"error": str(e)},
            )
            return jsonify({"error": "Failed to list rate limit configs"}), 500

    @api.get(
        "/configs/<rule_id>", responses={"200": RateLimitResponse, 401: ErrorResponse}
    )
    def get_rate_limit_config(rule_id: str):
        """
        Get a specific rate limit configuration.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            config = RateLimitConfig.objects(rule_id=rule_id).first()
            if not config:
                return jsonify(
                    {"error": f"Rate limit config '{rule_id}' not found"}
                ), 404

            return jsonify(config.to_dict()), 200

        except Exception as e:
            logger.log_error(
                "Error getting rate limit config",
                exception=e,
                context={"error": str(e), "rule_id": rule_id},
            )
            return jsonify({"error": "Failed to get rate limit config"}), 500

    @api.patch(
        "/configs/<rule_id>", responses={"200": RateLimitResponse, 401: ErrorResponse}
    )
    def update_rate_limit_config(rule_id: str):
        """
        Update a specific rate limit configuration.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            config = RateLimitConfig.objects(rule_id=rule_id).first()
            if not config:
                return jsonify(
                    {"error": f"Rate limit config '{rule_id}' not found"}
                ), 404

            body = request.get_json()
            req = RateLimitUpdateRequest(**body)

            # Update fields
            if req.max_requests is not None:
                config.max_requests = req.max_requests
            if req.window_size is not None:
                config.window_size = req.window_size
            if req.unit is not None:
                config.unit = req.unit.value
            if req.http_method is not None:
                config.http_method = req.http_method
            if req.description is not None:
                config.description = req.description
            if req.is_active is not None:
                config.is_active = req.is_active
            if req.priority is not None:
                config.priority = req.priority

            config.updated_by = g.user
            config.clean()
            config.save()

            logger.log_app_event(
                f"Rate limit config updated: {rule_id} by {g.user_id}",
                context={"rule_id": rule_id, "user_id": g.user_id},
            )

            return jsonify(config.to_dict()), 200

        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.log_error(
                "Error updating rate limit config",
                exception=e,
                context={"error": str(e), "rule_id": rule_id},
            )
            return jsonify({"error": "Failed to update rate limit config"}), 500

    @api.post(
        "/configs/<rule_id>/toggle",
        responses={"200": RateLimitResponse, 401: ErrorResponse},
    )
    def toggle_rate_limit_config(rule_id: str):
        """
        Toggle the active status of a rate limit configuration.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            config = RateLimitConfig.objects(rule_id=rule_id).first()
            if not config:
                return jsonify(
                    {"error": f"Rate limit config '{rule_id}' not found"}
                ), 404

            config.is_active = not config.is_active
            config.updated_by = g.user
            config.save()

            logger.log_app_event(
                f"Rate limit config toggled: {rule_id} (is_active={config.is_active}) by {g.user_id}",
                context={
                    "rule_id": rule_id,
                    "is_active": config.is_active,
                    "user_id": g.user_id,
                },
            )

            return jsonify(config.to_dict()), 200

        except Exception as e:
            logger.log_error(
                "Error toggling rate limit config",
                exception=e,
                context={"error": str(e), "rule_id": rule_id},
            )
            return jsonify({"error": "Failed to toggle rate limit config"}), 500

    @api.delete(
        "/configs/<rule_id>",
        responses={"200": RateLimitDeleteResponse, 401: ErrorResponse},
    )
    def delete_rate_limit_config(rule_id: str):
        """
        Delete a rate limit configuration.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            config = RateLimitConfig.objects(rule_id=rule_id).first()
            if not config:
                return jsonify(
                    {"error": f"Rate limit config '{rule_id}' not found"}
                ), 404

            config.delete()

            logger.log_app_event(
                f"Rate limit config deleted: {rule_id} by {g.user_id}",
                context={"rule_id": rule_id, "user_id": g.user_id},
            )

            return jsonify({"message": f"Rate limit config '{rule_id}' deleted"}), 200

        except Exception as e:
            logger.log_error(
                "Error deleting rate limit config",
                exception=e,
                context={"error": str(e), "rule_id": rule_id},
            )
            return jsonify({"error": "Failed to delete rate limit config"}), 500

    # ==================== BULK OPERATIONS ====================

    @api.post(
        "/configs/bulk/update",
        responses={"200": BulkRateLimitUpdateResponse, 401: ErrorResponse},
    )
    def bulk_update_rate_limits():
        """
        Bulk update multiple rate limit configurations.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            body = request.get_json()
            req = BulkRateLimitUpdateRequest(**body)

            updated_count = 0
            failed_count = 0

            for rule_id in req.rule_ids:
                try:
                    config = RateLimitConfig.objects(rule_id=rule_id).first()
                    if not config:
                        failed_count += 1
                        continue

                    # Apply updates
                    if req.updates.max_requests is not None:
                        config.max_requests = req.updates.max_requests
                    if req.updates.window_size is not None:
                        config.window_size = req.updates.window_size
                    if req.updates.unit is not None:
                        config.unit = req.updates.unit.value
                    if req.updates.http_method is not None:
                        config.http_method = req.updates.http_method
                    if req.updates.description is not None:
                        config.description = req.updates.description
                    if req.updates.is_active is not None:
                        config.is_active = req.updates.is_active
                    if req.updates.priority is not None:
                        config.priority = req.updates.priority

                    config.updated_by = g.user
                    config.clean()
                    config.save()
                    updated_count += 1

                except Exception as e:
                    logger.log_error(
                        f"Error updating rule {rule_id}",
                        exception=e,
                        context={"error": str(e), "rule_id": rule_id},
                    )
                    failed_count += 1

            logger.log_app_event(
                f"Bulk updated {updated_count} rate limit configs by {g.user_id}",
                context={"updated_count": updated_count, "user_id": g.user_id},
            )

            return jsonify(
                {
                    "updated_count": updated_count,
                    "failed_count": failed_count,
                    "message": f"Updated {updated_count} configs, {failed_count} failed",
                }
            ), 200

        except Exception as e:
            logger.log_error(
                "Error in bulk update", exception=e, context={"error": str(e)}
            )
            return jsonify({"error": "Failed to bulk update rate limits"}), 500

    # ==================== RATE LIMIT COUNTERS ====================

    @api.post(
        "/counters/reset", responses={"200": RateLimitResetResponse, 401: ErrorResponse}
    )
    def reset_rate_limit_counter():
        """
        Manually reset a rate limit counter.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            body = request.get_json()
            req = RateLimitResetRequest(**body)

            service = get_rate_limit_service()
            success = service.reset_counter(
                scope=req.scope,
                target=req.target or "",
                route=req.route,
                method=req.method or "all",
            )

            if success:
                logger.log_app_event(
                    f"Rate limit counter reset: scope={req.scope}, target={req.target}, route={req.route} by {g.user_id}",
                    context={
                        "scope": req.scope,
                        "target": req.target,
                        "route": req.route,
                        "user_id": g.user_id,
                    },
                )
                return jsonify(
                    {
                        "success": True,
                        "message": "Rate limit counter reset successfully",
                    }
                ), 200
            else:
                return jsonify(
                    {
                        "success": False,
                        "message": "Failed to reset rate limit counter",
                    }
                ), 500

        except Exception as e:
            logger.log_error(
                "Error resetting rate limit counter",
                exception=e,
                context={"error": str(e)},
            )
            return jsonify({"error": "Failed to reset counter"}), 500

    # ==================== RATE LIMIT LOGS ====================

    @api.get("/logs", responses={"200": RateLimitLogsListResponse, 401: ErrorResponse})
    def get_rate_limit_logs():
        """
        Get rate limit logs with optional filtering.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            query = RateLimitLog.objects()
            filters = {}

            # Apply filters
            user_id = request.args.get("user_id")
            if user_id:
                query = query.filter(user_id=user_id)
                filters["user_id"] = user_id

            organization_id = request.args.get("organization_id")
            if organization_id:
                query = query.filter(organization_id=organization_id)
                filters["organization_id"] = organization_id

            route_pattern = request.args.get("route_pattern")
            if route_pattern:
                query = query.filter(route_pattern=route_pattern)
                filters["route_pattern"] = route_pattern

            blocked = request.args.get("blocked")
            if blocked is not None:
                blocked_bool = blocked.lower() in ("true", "1", "yes")
                query = query.filter(blocked=blocked_bool)
                filters["blocked"] = blocked_bool

            # Pagination
            page = int(request.args.get("page", 1))
            per_page = int(request.args.get("per_page", 50))

            total = query.count()
            logs = (
                query.skip((page - 1) * per_page).limit(per_page).order_by("-timestamp")
            )

            log_dicts = []
            for log in logs:
                log_dicts.append(
                    {
                        "user_id": log.user_id,
                        "organization_id": log.organization_id,
                        "route_pattern": log.route_pattern,
                        "http_method": log.http_method,
                        "ip_address": log.ip_address,
                        "rule_id": log.rule_id,
                        "blocked": log.blocked,
                        "request_count": log.request_count,
                        "max_allowed": log.max_allowed,
                        "timestamp": log.timestamp.isoformat()
                        if log.timestamp
                        else None,
                    }
                )

            return jsonify(
                {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "logs": log_dicts,
                    "filters": filters,
                }
            ), 200

        except Exception as e:
            logger.log_error(
                "Error getting rate limit logs", exception=e, context={"error": str(e)}
            )
            return jsonify({"error": "Failed to get rate limit logs"}), 500

    # ==================== RATE LIMIT STATUS ====================

    @api.get("/status", responses={"200": RateLimitStatusResponse, 401: ErrorResponse})
    def get_rate_limit_status():
        """
        Get current rate limit configuration status.
        """
        # Check authentication
        user, error, status_code = _require_super_admin()
        if error:
            return error, status_code

        try:
            user_id = request.args.get("user_id")
            organization_id = request.args.get("organization_id")
            route_pattern = request.args.get("route_pattern")

            service = get_rate_limit_service()
            status = service.get_rate_limit_status(
                user_uuid=user_id,
                organization_uuid=organization_id,
                route_pattern=route_pattern,
            )

            return jsonify(status), 200

        except Exception as e:
            logger.log_error(
                "Error getting rate limit status",
                exception=e,
                context={"error": str(e)},
            )
            return jsonify({"error": "Failed to get rate limit status"}), 500

    return api
