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
        if meta["required"] and qid not in answers:
            errors[qid] = "This field is required."
    unknown = sorted(set(answers) - set(index))
    for key in unknown:
        errors[key] = "Unknown question id."
    return (len(errors) == 0), errors

