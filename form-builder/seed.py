import json
from app import app, db

def seed_and_verify():
    # Use Flask's test client to run requests without needing a external server process
    client = app.test_client()

    print("=== Step 1: Create a Theme Template ===")
    theme_payload = {
        "name": "Midnight Ocean",
        "active": True,
        "style": {
            "font_family": "Outfit, sans-serif",
            "background_gradient": "linear-gradient(135deg, #0f2027, #203a43, #2c5364)",
            "primary_color": "#00d2ff",
            "secondary_color": "#00d2ff",
            "surface_color": "rgba(255, 255, 255, 0.05)",
            "text_color": "#ffffff",
            "border_radius": "12px",
            "backdrop_blur": "10px",
            "animation_speed": "0.3s"
        }
    }
    
    theme_res = client.post("/api/themes", json=theme_payload)
    theme_data = json.loads(theme_res.data)
    print(f"Theme Created. ID: {theme_data.get('_id')}\n")

    print("=== Step 2: Insert Customer Feedback Form ===")
    form_payload = {
        "title": "Customer Feedback Form",
        "description": "Evaluate our service quality and calculate performance satisfaction",
        "theme_id": theme_data.get("_id"),
        "questions": [
            {
                "id": "q_satisfaction",
                "type": "multiple_choice",
                "title": "How satisfied are you with our service?",
                "required": True,
                "hint": "Please choose one option",
                "properties": {
                    "choices": [
                        {"value": "Very Satisfied", "score": 10},
                        {"value": "Neutral", "score": 5},
                        {"value": "Dissatisfied", "score": 1}
                    ]
                }
            },
            {
                "id": "q_nps",
                "type": "range",
                "title": "Likelihood to recommend (NPS)",
                "required": True,
                "properties": {
                    "min": 1,
                    "max": 10,
                    "step": 1
                }
            },
            {
                "id": "q_comments",
                "type": "text",
                "title": "Do you have any comments?",
                "required": False,
                "properties": {
                    "min_length": 5,
                    "max_length": 500
                }
            },
            {
                "id": "q_camera_capture",
                "type": "camera",
                "title": "Upload photo profile",
                "required": False
            },
            {
                "id": "q_overall_index",
                "type": "calculation",
                "calculation_formula": "(q_nps * 0.4) + q_satisfaction_score"
            }
        ]
    }
    
    form_res = client.post("/api/forms", json=form_payload)
    form_data = json.loads(form_res.data)
    form_id = form_data.get("_id")
    print(f"Form Created. ID: {form_id}\n")

    print("=== Step 3: Query SurveyJS Translation API ===")
    surveyjs_res = client.get(f"/api/forms/{form_id}/surveyjs")
    surveyjs_schema = json.loads(surveyjs_res.data)
    print(json.dumps(surveyjs_schema, indent=2))
    print("\n")

    print("=== Step 4: Post Mock Submission ===")
    # Base64 string representing a simple PNG placeholder image for the camera field
    mock_base64_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    
    submission_payload = {
        "q_satisfaction": "Very Satisfied",
        "q_nps": 9,
        "q_comments": "Wonderful service! The interface is beautiful.",
        "q_camera_capture": mock_base64_image
    }
    
    submit_res = client.post(f"/api/forms/{form_id}/submit", json=submission_payload)
    submission_result = json.loads(submit_res.data)
    
    print("Submission Result:")
    print(json.dumps(submission_result, indent=2))

if __name__ == "__main__":
    seed_and_verify()
