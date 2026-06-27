class SchemaDriftDetector:
    @classmethod
    def detect_drift(cls, existing_form, new_sections):
        """
        Compares new sections structure with the active published version sections.
        Returns a list of warning dictionaries:
        [{"type": "question_deleted" | "type_changed", "question_id": "...", "details": "..."}]
        """
        warnings = []
        versions = existing_form.get("versions", [])
        current_version_num = existing_form.get("current_version", 1)

        # Get current published version
        current_version = None
        for v in versions:
            if v.get("version_number") == current_version_num:
                current_version = v
                break
        
        if not current_version:
            return warnings # No historical published version to compare

        # Extract current questions
        current_questions = {}
        for sec in current_version.get("sections", []):
            for q in sec.get("questions", []):
                current_questions[q.get("id")] = q

        # Extract new questions
        new_questions = {}
        for sec in new_sections:
            for q in sec.get("questions", []):
                new_questions[q.get("id")] = q

        # 1. Check for deleted questions
        for q_id, q_node in current_questions.items():
            if q_id not in new_questions:
                warnings.append({
                    "type": "question_deleted",
                    "question_id": q_id,
                    "details": f"Question '{q_id}' has been removed. Existing submissions will lose representation."
                })

        # 2. Check for type changes
        for q_id, new_node in new_questions.items():
            if q_id in current_questions:
                old_node = current_questions[q_id]
                old_type = old_node.get("type")
                new_type = new_node.get("type")
                
                if old_type != new_type:
                    warnings.append({
                        "type": "type_changed",
                        "question_id": q_id,
                        "details": f"Question '{q_id}' type shifted from '{old_type}' to '{new_type}'. This may break analytics."
                    })

        return warnings

    @classmethod
    def generate_migration_plan(cls, existing_form, new_sections):
        """
        Compares the new sections with the current published version and generates
        a plan containing actions to safely type-cast responses for compatibility.
        """
        plan = {
            "form_id": str(existing_form.get("_id")),
            "actions": []
        }
        
        versions = existing_form.get("versions", [])
        current_version_num = existing_form.get("current_version", 1)

        current_version = None
        for v in versions:
            if v.get("version_number") == current_version_num:
                current_version = v
                break
        
        if not current_version:
            return plan

        current_questions = {}
        for sec in current_version.get("sections", []):
            for q in sec.get("questions", []):
                current_questions[q.get("id")] = q

        new_questions = {}
        for sec in new_sections:
            for q in sec.get("questions", []):
                new_questions[q.get("id")] = q

        for q_id, new_node in new_questions.items():
            if q_id in current_questions:
                old_node = current_questions[q_id]
                old_type = old_node.get("type")
                new_type = new_node.get("type")
                
                if old_type != new_type:
                    cast_to = None
                    if new_type in ["number", "range"]:
                        cast_to = "number"
                    elif new_type in ["text", "multiple_choice", "comment"]:
                        cast_to = "string"
                    
                    if cast_to:
                        plan["actions"].append({
                            "type": "cast_type",
                            "question_id": q_id,
                            "from_type": old_type,
                            "to_type": new_type,
                            "cast_to": cast_to
                        })
        return plan

    @classmethod
    def execute_migration_plan(cls, db, plan):
        """
        Asynchronously or synchronously runs data reconciliation actions on the
        responses collection based on the generated migration plan.
        """
        if not plan or not plan.get("actions"):
            return
        
        from bson import ObjectId
        import logging
        logger = logging.getLogger("SchemaDriftDetector")
        
        form_id = plan["form_id"]
        actions = plan["actions"]
        responses_col = db["responses"]
        
        for action in actions:
            q_id = action["question_id"]
            action_type = action["type"]
            
            if action_type == "cast_type":
                cast_to = action.get("cast_to")
                try:
                    cursor = responses_col.find({
                        "form_id": ObjectId(form_id),
                        f"answers.{q_id}": {"$exists": True}
                    })
                    for resp in cursor:
                        val = resp["answers"].get(q_id)
                        new_val = val
                        try:
                            if cast_to == "number":
                                if isinstance(val, str):
                                    new_val = float(val) if "." in val else int(val)
                            elif cast_to == "string":
                                new_val = str(val)
                        except Exception:
                            pass
                        
                        if new_val != val:
                            responses_col.update_one(
                                {"_id": resp["_id"]},
                                {"$set": {f"answers.{q_id}": new_val}}
                            )
                except Exception as e:
                    logger.warning(f"Failed to auto-migrate field {q_id} for form {form_id}: {str(e)}")
