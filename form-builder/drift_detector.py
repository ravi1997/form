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
