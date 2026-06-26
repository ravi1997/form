import logging
import urllib.request
import json
from bson import ObjectId

logger = logging.getLogger("LookupResolver")

class LookupResolver:
    @classmethod
    def resolve_lookup_choices(cls, db, lookup_config, org_id):
        """
        Queries MongoDB responses or queries external REST APIs to fetch choice lists.
        lookup_config: {"form_id": "string", "field_id": "string"} OR
                       {"external_source": {"url": "string", "value_path": "string"}}
        """
        if not lookup_config:
            return []

        # We strictly block calling external API sources as lookups are only allowed internal to the server.
        if lookup_config.get("external_source"):
            return []

        # --- INTERNAL CROSS-FORM LOOKUP ---
        form_id_str = lookup_config.get("form_id")
        field_id = lookup_config.get("field_id")

        if db is None or not form_id_str or not field_id:
            return []

        try:
            form_id = ObjectId(form_id_str)
        except Exception:
            logger.warning(f"Invalid lookup form_id format: {form_id_str}")
            return []

        # Enforce strict cross-form access permissions and tenant boundaries
        from flask import has_request_context, request
        import os
        if os.getenv("REQUIRE_AUTH") == "true" and has_request_context():
            user_ctx = getattr(request, "user_context", None)
            if user_ctx:
                user_id = user_ctx.get("user_id")
                user_email = user_ctx.get("email")
                user_roles = user_ctx.get("roles", [])
                
                if "Admin" not in user_roles:
                    target_form = db["forms"].find_one({"_id": form_id})
                    if not target_form:
                        return []
                    
                    shares = target_form.get("shares", [])
                    has_share_access = any(
                        s.get("user_id") == user_id or s.get("email") == user_email
                        for s in shares
                    )
                    
                    if target_form.get("organization_id") != org_id:
                        if not has_share_access:
                            logger.warning(f"Cross-tenant lookup denied: user {user_id} lacks access to form {form_id}")
                            return []
                    else:
                        if shares and not has_share_access:
                            logger.warning(f"Lookup denied: user {user_id} not shared on form {form_id}")
                            return []

        target_form = db["forms"].find_one({"_id": form_id})
        settings = target_form.get("lookup_settings", {}) if target_form else {}
        timeout_ms = settings.get("max_timeout_ms", 1000)
        use_mv = settings.get("use_materialized_view", True)

        if use_mv:
            mv = db["lookup_materialized_views"].find_one({"form_id": form_id, "field_id": field_id})
            if mv:
                return mv.get("choices", [])

        try:
            pipeline = [
                {
                    "$match": {
                        "form_id": form_id,
                        "organization_id": org_id,
                        "status": "Submitted"
                    }
                },
                {
                    "$group": {
                        "_id": f"$answers.{field_id}"
                    }
                },
                {
                    "$match": {
                        "_id": {"$ne": None, "$ne": ""}
                    }
                }
            ]

            results = list(db["responses"].aggregate(pipeline, maxTimeMS=timeout_ms))
            choices = []
            for r in results:
                val = r.get("_id")
                choices.append({
                    "value": val,
                    "text": str(val)
                })
            
            choices.sort(key=lambda x: str(x["value"]))

            from datetime import datetime
            db["lookup_materialized_views"].update_one(
                {"form_id": form_id, "field_id": field_id},
                {"$set": {
                    "organization_id": org_id,
                    "choices": choices,
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            return choices
        except Exception as e:
            logger.error(f"Failed to resolve choices lookup: {str(e)}")
            return []

    @classmethod
    def update_materialized_view(cls, db, form_id, field_id, org_id, timeout_ms=1000):
        try:
            pipeline = [
                {
                    "$match": {
                        "form_id": form_id,
                        "organization_id": org_id,
                        "status": "Submitted"
                    }
                },
                {
                    "$group": {
                        "_id": f"$answers.{field_id}"
                    }
                },
                {
                    "$match": {
                        "_id": {"$ne": None, "$ne": ""}
                    }
                }
            ]
            results = list(db["responses"].aggregate(pipeline, maxTimeMS=timeout_ms))
            choices = []
            for r in results:
                val = r.get("_id")
                choices.append({
                    "value": val,
                    "text": str(val)
                })
            choices.sort(key=lambda x: str(x["value"]))
            
            from datetime import datetime
            db["lookup_materialized_views"].update_one(
                {"form_id": form_id, "field_id": field_id},
                {"$set": {
                    "organization_id": org_id,
                    "choices": choices,
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            return choices
        except Exception as e:
            logger.error(f"Failed to update materialized view: {str(e)}")
            return []
