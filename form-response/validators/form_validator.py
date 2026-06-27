from __future__ import annotations


def build_question_index(form_json: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for section in form_json.get("sections", []):
        for question in section.get("questions", []):
            qid = question.get("id")
            if qid:
                index[qid] = {
                    "id": qid,
                    "type": question.get("type"),
                    "required": bool(question.get("required", False)),
                    "choices": question.get("choices", []),
                }
    return index


def minimal_form_snapshot(form_json: dict) -> dict:
    return {
        "form_id": str(form_json.get("id") or form_json.get("_id")),
        "title": form_json.get("title", "Untitled Form"),
        "sections": [
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "questions": [
                    {
                        "id": q.get("id"),
                        "type": q.get("type"),
                        "required": bool(q.get("required", False)),
                        "choices": q.get("choices", []),
                    }
                    for q in section.get("questions", [])
                ],
            }
            for section in form_json.get("sections", [])
        ],
    }


def validate_response_payload(form_snapshot: dict, answers: dict) -> tuple[bool, dict]:
    errors: dict[str, str] = {}
    index = build_question_index(form_snapshot)
    for qid, meta in index.items():
        if meta["required"] and (qid not in answers or answers[qid] is None or answers[qid] == ""):
            errors[qid] = "This field is required."
            continue
        
        if qid in answers:
            val = answers[qid]
            if val is None:
                continue
            
            qtype = meta.get("type")
            choices = meta.get("choices") or []
            
            if qtype == "number":
                if not isinstance(val, (int, float)):
                    errors[qid] = "Value must be a number."
            elif qtype in ("choice", "single_choice", "select"):
                if choices and val not in choices:
                    errors[qid] = f"Value must be one of the allowed choices: {choices}."
            elif qtype in ("multiple_choice", "multi_select"):
                if not isinstance(val, list):
                    errors[qid] = "Value must be a list of choices."
                elif choices:
                    invalid_choices = [v for v in val if v not in choices]
                    if invalid_choices:
                        errors[qid] = f"Values {invalid_choices} are not in the allowed choices: {choices}."
            elif qtype in ("boolean", "checkbox"):
                if not isinstance(val, bool):
                    errors[qid] = "Value must be a boolean."
            elif qtype == "text":
                if not isinstance(val, str):
                    errors[qid] = "Value must be a string."

    unknown = sorted(set(answers) - set(index))
    for key in unknown:
        errors[key] = "Unknown question id."
    return (len(errors) == 0), errors

