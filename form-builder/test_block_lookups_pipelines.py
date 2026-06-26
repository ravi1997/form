import unittest
import json
from bson import ObjectId
from app import app, db

class TestBlockLookupsAndPipelines(unittest.TestCase):
    def test_block_script_engine_logic(self):
        # Design a form with a Block script.
        # IF q_vip == "Yes" THEN set q_discount = 20
        # ELSE set q_discount = 0
        form_payload = {
            "title": "VIP Club",
            "block_script": {
                "blocks": [
                    {
                        "type": "conditional",
                        "condition": {
                            "field": "q_vip",
                            "operator": "==",
                            "value": "Yes"
                        },
                        "then_actions": [
                            {
                                "type": "set_value",
                                "field_id": "q_discount",
                                "value": 20
                            }
                        ],
                        "else_actions": [
                            {
                                "type": "set_value",
                                "field_id": "q_discount",
                                "value": 0
                            }
                        ]
                    }
                ]
            },
            "sections": [
                {
                    "id": "s1",
                    "questions": [
                        {"id": "q_vip", "type": "multiple_choice", "properties": {"choices": ["Yes", "No"]}},
                        {"id": "q_discount", "type": "number"}
                    ]
                }
            ]
        }

        client = app.test_client()
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Case A: VIP is Yes -> discount becomes 20
        res_submit = client.post(f"/api/forms/{form_id}/submit", json={"q_vip": "Yes"})
        data = json.loads(res_submit.data)
        self.assertEqual(data["response"]["answers"]["q_discount"], 20)

        # Case B: VIP is No -> discount becomes 0
        res_submit_no = client.post(f"/api/forms/{form_id}/submit", json={"q_vip": "No"})
        data_no = json.loads(res_submit_no.data)
        self.assertEqual(data_no["response"]["answers"]["q_discount"], 0)

    def test_internal_cross_form_lookups(self):
        client = app.test_client()
        
        # 1. Create a Source Form (e.g. Products list)
        source_form_payload = {
            "title": "Products Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_name", "type": "text", "required": True}]
                }
            ]
        }
        res_src = client.post("/api/forms", json=source_form_payload)
        src_form = json.loads(res_src.data)
        src_form_id = src_form["_id"]

        # 2. Add some submissions representing products
        client.post(f"/api/forms/{src_form_id}/submit", json={"q_name": "Laptop Pro"})
        client.post(f"/api/forms/{src_form_id}/submit", json={"q_name": "Tablet Air"})

        # 3. Create a Destination Form with a Dropdown lookup referencing the Source Form
        dest_form_payload = {
            "title": "Orders Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [
                        {
                            "id": "q_product_selected",
                            "type": "dropdown",
                            "properties": {
                                "lookup": {
                                    "form_id": src_form_id,
                                    "field_id": "q_name"
                                }
                            }
                        }
                    ]
                }
            ]
        }
        res_dest = client.post("/api/forms", json=dest_form_payload)
        dest_form = json.loads(res_dest.data)
        dest_form_id = dest_form["_id"]

        # 4. Fetch translated SurveyJS schema. Choices should be resolved dynamically!
        res_sjs = client.get(f"/api/forms/{dest_form_id}/surveyjs")
        sjs = json.loads(res_sjs.data)
        choices = sjs["pages"][0]["elements"][0]["choices"]
        
        self.assertEqual(len(choices), 2)
        self.assertEqual(choices[0]["value"], "Laptop Pro")
        self.assertEqual(choices[1]["value"], "Tablet Air")

if __name__ == "__main__":
    unittest.main()
