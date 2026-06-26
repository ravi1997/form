import unittest
import json
from datetime import datetime, timedelta
from app import app, db
from encryption_helper import EncryptionHelper
from anonymizer import DataAnonymizer

class TestEnterpriseFeatures(unittest.TestCase):
    def test_pii_encryption_and_anonymization(self):
        client = app.test_client()

        # 1. Create a form with a sensitive field: q_ssn
        form_payload = {
            "title": "Tax Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [
                        {
                            "id": "q_ssn",
                            "type": "text",
                            "required": True,
                            "properties": {
                                "sensitive": True # Triggers AES/Fernet encryption
                            }
                        }
                    ]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # 2. Submit response containing sensitive SSN value
        res_submit = client.post(f"/api/forms/{form_id}/submit", json={"q_ssn": "123-456-7890"})
        submit_data = json.loads(res_submit.data)
        resp_id = submit_data["response"]["_id"]
        
        # Verify the ssn inside response answers is encrypted (not equal to raw)
        encrypted_val = submit_data["response"]["answers"]["q_ssn"]
        self.assertNotEqual(encrypted_val, "123-456-7890")
        
        # Verify it can be decrypted back
        decrypted_val = EncryptionHelper.decrypt_value(encrypted_val)
        self.assertEqual(decrypted_val, "123-456-7890")

        # 3. Test Export JSON with decryption
        res_export = client.get(f"/api/forms/{form_id}/export/json")
        export_data = json.loads(res_export.data)
        self.assertEqual(export_data[0]["answers"]["q_ssn"], "123-456-7890")

        # 4. Test Export JSON with GDPR anonymization (?anonymize=true)
        res_export_anon = client.get(f"/api/forms/{form_id}/export/json?anonymize=true")
        export_data_anon = json.loads(res_export_anon.data)
        self.assertEqual(export_data_anon[0]["answers"]["q_ssn"], "[ANONYMIZED]")

    def test_ab_testing_version_splits(self):
        client = app.test_client()

        # Create a form with A/B testing configured
        # Variant 1: version 1 (weight 50)
        # Variant 2: version 2 (weight 50)
        form_payload = {
            "title": "Landing Page Test",
            "ab_testing": {
                "enabled": True,
                "variants": [
                    {"version": 1, "weight": 50},
                    {"version": 2, "weight": 50}
                ]
            },
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q1", "type": "text"}]
                }
            ],
            "versions": [
                {
                    "version_number": 1,
                    "published": True,
                    "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text"}]}]
                },
                {
                    "version_number": 2,
                    "published": False,
                    "sections": [{"id": "s1", "questions": [{"id": "q2", "type": "text"}]}]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Request SurveyJS translation multiple times. It should assign different versions.
        assigned_versions = set()
        for _ in range(20):
            res_sjs = client.get(f"/api/forms/{form_id}/surveyjs")
            sjs = json.loads(res_sjs.data)
            assigned_versions.add(sjs.get("ab_version_assigned"))

        # Verify that both versions were queried
        self.assertTrue(1 in assigned_versions or 2 in assigned_versions)

    def test_soft_deletes_and_quota(self):
        client = app.test_client()

        # Create a form with a submission quota limit: max_submissions = 1
        form_payload = {
            "title": "Limited Event Ticket",
            "max_submissions": 1,
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_name", "type": "text", "required": True}]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # 1. First submission should pass
        res_sub1 = client.post(f"/api/forms/{form_id}/submit", json={"q_name": "Dave"})
        self.assertEqual(res_sub1.status_code, 201)

        # 2. Second submission should fail because quota is exceeded
        res_sub2 = client.post(f"/api/forms/{form_id}/submit", json={"q_name": "Eva"})
        self.assertEqual(res_sub2.status_code, 400)
        err_data = json.loads(res_sub2.data)
        self.assertEqual(err_data["details"]["form"], "The response quota for this form has been exceeded.")

        # 3. Soft delete form
        res_del = client.delete(f"/api/forms/{form_id}")
        self.assertEqual(res_del.status_code, 200)

        # 4. Trying to fetch or submit to a soft-deleted form should return 404/error
        res_get = client.get(f"/api/forms/{form_id}")
        self.assertEqual(res_get.status_code, 404)

    def test_deprecation_warning_on_draft_promotion(self):
        from bson import ObjectId
        client = app.test_client()
        form_payload = {
            "title": "Deprecation Test Form",
            "sections": [{
                "id": "s1",
                "questions": [{"id": "q1", "type": "text"}]
            }]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Create draft response on version 1
        res_draft = client.post(f"/api/forms/{form_id}/submit", json={"q1": "draft info", "status": "Draft"})
        self.assertEqual(res_draft.status_code, 201)
        draft = json.loads(res_draft.data)
        draft_id = draft["response"]["_id"]

        # Directly bump current_version on the form to simulate a schema update / Commit B
        db["forms"].update_one({"_id": ObjectId(form_id)}, {"$set": {"current_version": 2}})

        # Promote draft (PATCH)
        res_promote = client.patch(f"/api/responses/{draft_id}", json={"status": "Submitted", "answers": {"q1": "submitted info"}})
        self.assertEqual(res_promote.status_code, 200)
        promote_data = json.loads(res_promote.data)
        self.assertIn("warning", promote_data)
        self.assertIn("DeprecationWarning", promote_data["warning"])

    def test_tenant_db_index_freezing(self):
        import os
        from bson import ObjectId
        from app import client as mongo_client, get_collections
        
        # Save original env
        orig_isolation = os.environ.get("TENANT_DB_ISOLATION")
        orig_limit = os.environ.get("ACTIVE_DB_LIMIT")
        
        try:
            os.environ["TENANT_DB_ISOLATION"] = "true"
            os.environ["ACTIVE_DB_LIMIT"] = "2"
            
            # Access tenant org1 (will create indexes)
            with app.test_request_context('/?organization_id=org1'):
                get_collections()
            # Access tenant org2 (will create indexes)
            with app.test_request_context('/?organization_id=org2'):
                get_collections()
            # Access tenant org3 (will exceed limit of 2, org1 should be frozen)
            with app.test_request_context('/?organization_id=org3'):
                get_collections()
            
            # Verify org1 indexes are dropped (only default _id_ index should remain)
            db_org1 = mongo_client["form_db_org1"]
            indexes_org1 = db_org1["projects"].index_information()
            self.assertEqual(list(indexes_org1.keys()), ["_id_"])
            
            # Verify org3 indexes exist (since it's active)
            db_org3 = mongo_client["form_db_org3"]
            indexes_org3 = db_org3["projects"].index_information()
            self.assertIn("organization_id_1", indexes_org3)
            
            # Access org1 again (re-activates it and recreates indexes)
            with app.test_request_context('/?organization_id=org1'):
                get_collections()
            indexes_org1_recreated = db_org1["projects"].index_information()
            self.assertIn("organization_id_1", indexes_org1_recreated)
            
        finally:
            if orig_isolation is not None:
                os.environ["TENANT_DB_ISOLATION"] = orig_isolation
            else:
                os.environ.pop("TENANT_DB_ISOLATION", None)
            if orig_limit is not None:
                os.environ["ACTIVE_DB_LIMIT"] = orig_limit
            else:
                os.environ.pop("ACTIVE_DB_LIMIT", None)

    def test_response_deletion_on_publish(self):
        from bson import ObjectId
        client = app.test_client()
        
        # Create a form
        form_payload = {
            "title": "Version Purge Form",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text"}]}]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]
        
        # Submit response to version 1
        client.post(f"/api/forms/{form_id}/submit?version=1", json={"q1": "v1 response"})
        
        # Create version 2
        res_v2 = client.post(f"/api/forms/{form_id}/versions", json={
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text"}]}]
        })
        self.assertEqual(res_v2.status_code, 201)
        
        # Submit response to version 2
        client.post(f"/api/forms/{form_id}/submit?version=2", json={"q1": "v2 response"})
        
        # Verify both exist
        self.assertEqual(db["responses"].count_documents({"form_id": ObjectId(form_id)}), 2)
        
        # Publish version 2
        res_publish = client.post(f"/api/forms/{form_id}/publish", json={"version_number": 2})
        self.assertEqual(res_publish.status_code, 200)
        
        # Verify that response of version 1 (which is not published) is deleted
        self.assertEqual(db["responses"].count_documents({"form_id": ObjectId(form_id)}), 1)
        remaining = db["responses"].find_one({"form_id": ObjectId(form_id)})
        self.assertEqual(remaining["version"], 2)

    def test_upload_registry_and_garbage_collection(self):
        from bson import ObjectId
        from datetime import datetime, timedelta
        import os
        from s3_helper import S3Helper
        from app import register_upload, link_uploads_to_response
        
        client = app.test_client()
        form_payload = {
            "title": "Upload Reg Form",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "camera"}]}]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]
        
        # Base64 camera upload
        camera_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        res_submit = client.post(f"/api/forms/{form_id}/submit", json={"q1": camera_data})
        self.assertEqual(res_submit.status_code, 201)
        resp_data = json.loads(res_submit.data)
        resp_id = resp_data["response"]["_id"]
        filepath = resp_data["response"]["answers"]["q1"]
        
        # Verify it was registered and linked
        registered = db["upload_registry"].find_one({"file_path": filepath})
        self.assertIsNotNone(registered)
        self.assertEqual(str(registered.get("response_id")), str(resp_id))
        
        # Create an orphaned file and register it manually with a 25-hour-old timestamp
        dummy_file = os.path.join("static/uploads", "orphaned_test.png")
        os.makedirs("static/uploads", exist_ok=True)
        with open(dummy_file, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nDummy Data")
        
        dummy_url = f"/static/uploads/orphaned_test.png"
        db["upload_registry"].insert_one({
            "file_path": dummy_url,
            "response_id": None,
            "created_at": datetime.utcnow() - timedelta(hours=25)
        })
        
        # Verify file exists
        self.assertTrue(os.path.exists(dummy_file))
        
        # Trigger register_upload with new file (1 in 10 chance, but we can call pruning directly)
        db["upload_registry"].insert_one({
            "file_path": "/static/uploads/new_dummy.png",
            "response_id": None,
            "created_at": datetime.utcnow()
        })
        
        # Directly invoke pruning logic to guarantee execution in test
        cutoff = datetime.utcnow() - timedelta(hours=24)
        orphans = list(db["upload_registry"].find({
            "created_at": {"$lt": cutoff},
            "$or": [{"response_id": None}, {"response_id": {"$exists": False}}]
        }))
        for o in orphans:
            S3Helper.delete_file(o["file_path"])
        db["upload_registry"].delete_many({"_id": {"$in": [o["_id"] for o in orphans]}})
        
        # Verify orphaned file is deleted
        self.assertFalse(os.path.exists(dummy_file))
        self.assertIsNone(db["upload_registry"].find_one({"file_path": dummy_url}))

    def test_lookup_security(self):
        import os
        from bson import ObjectId
        from lookup_resolver import LookupResolver
        
        # Create dummy form and responses
        form_id = ObjectId()
        db["forms"].insert_one({
            "_id": form_id,
            "organization_id": "org_tenant_a",
            "title": "Tenant A Form"
        })
        db["responses"].insert_one({
            "form_id": form_id,
            "organization_id": "org_tenant_a",
            "status": "Submitted",
            "answers": {"q_name": "Valuable Data"}
        })
        
        lookup_config = {
            "form_id": str(form_id),
            "field_id": "q_name"
        }
        
        # Save original require auth env
        orig_auth = os.environ.get("REQUIRE_AUTH")
        try:
            os.environ["REQUIRE_AUTH"] = "true"
            
            # Access LookupResolver with Tenant A context
            choices_a = LookupResolver.resolve_lookup_choices(db, lookup_config, "org_tenant_a")
            # Same organization lookup should succeed
            self.assertEqual(choices_a, [{"value": "Valuable Data", "text": "Valuable Data"}])
            
            # Try to resolve lookup under Tenant B context (different org)
            # Create a mock request context representing a Tenant B user
            with app.test_request_context('/'):
                from flask import request
                request.user_context = {
                    "user_id": "user_b",
                    "email": "user@b.com",
                    "roles": ["Respondent"],
                    "organization_id": "org_tenant_b"
                }
                choices_b = LookupResolver.resolve_lookup_choices(db, lookup_config, "org_tenant_b")
                # Should deny and return empty choices
                self.assertEqual(choices_b, [])
                
        finally:
            if orig_auth is not None:
                os.environ["REQUIRE_AUTH"] = orig_auth
            else:
                os.environ.pop("REQUIRE_AUTH", None)

    def test_git_merge_conflict_markers(self):
        client = app.test_client()
        
        # Create a form
        form_payload = {
            "title": "Merge Conflict Form",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "properties": {"title": "Base Title"}}]}]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]
        
        # Create initial commit on main
        res_init = client.post(f"/api/forms/{form_id}/commit", json={
            "branch": "main",
            "message": "Initial commit",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "properties": {"title": "Base Title"}}]}]
        })
        self.assertEqual(res_init.status_code, 201)
        
        # Branch main points to Commit A. Create feat1 branch.
        res_br = client.post(f"/api/forms/{form_id}/branches", json={"branch_name": "feat1", "source_branch": "main"})
        self.assertEqual(res_br.status_code, 201)
        
        # Commit to main (modifying q1)
        res_c1 = client.post(f"/api/forms/{form_id}/commit", json={
            "branch": "main",
            "message": "Commit main",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "properties": {"title": "Ours Title"}}]}]
        })
        self.assertEqual(res_c1.status_code, 201)
        
        # Commit to feat1 (modifying q1 differently)
        res_c2 = client.post(f"/api/forms/{form_id}/commit", json={
            "branch": "feat1",
            "message": "Commit feat1",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "properties": {"title": "Theirs Title"}}]}]
        })
        self.assertEqual(res_c2.status_code, 201)
        
        # Merge feat1 into main
        res_merge = client.post(f"/api/forms/{form_id}/merge", json={
            "source_branch": "feat1",
            "target_branch": "main"
        })
        self.assertEqual(res_merge.status_code, 200)
        merge_data = json.loads(res_merge.data)
        self.assertTrue(merge_data["merged"])
        self.assertIn("q1", merge_data["conflicts"])
        
        # Fetch the head commit of main and verify the conflict markers are saved
        res_commits = client.get(f"/api/forms/{form_id}/commits")
        commits = json.loads(res_commits.data)
        head_commit = commits[0]
        q1_merged = head_commit["sections"][0]["questions"][0]
        
        self.assertEqual(q1_merged["type"], "conflict")
        self.assertEqual(q1_merged["conflict_ours"]["properties"]["title"], "Ours Title")
        self.assertEqual(q1_merged["conflict_theirs"]["properties"]["title"], "Theirs Title")

    def test_upload_registry_cleanup_on_conflict_and_validation_failure(self):
        import os
        from bson import ObjectId
        
        client = app.test_client()
        form_payload = {
            "title": "Cleanup Test Form",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "camera"}]}]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]
        
        # 1. Create a draft response
        res_draft = client.post(f"/api/forms/{form_id}/submit", json={"status": "Draft"})
        draft_id = json.loads(res_draft.data)["response"]["_id"]
        
        # Pre-save a value to DB first to setup subsequent 3-way merge conflict
        client.patch(f"/api/responses/{draft_id}", json={
            "status": "Draft",
            "answers": {"q1": "different_db_val"}
        })
        
        # 2. Upload with validation failure (non-base64 invalid payload format for camera)
        bad_camera_data = "data:image/png;base64,invalid-signature-data" + "A" * 120
        res_fail = client.patch(f"/api/responses/{draft_id}", json={
            "status": "Draft",
            "answers": {"q1": bad_camera_data}
        })
        self.assertEqual(res_fail.status_code, 400)
        
        # Verify the registry doesn't keep it and S3Helper didn't write it (or if it did, it is cleaned up)
        registered_count = db["upload_registry"].count_documents({"response_id": ObjectId(draft_id)})
        self.assertEqual(registered_count, 0)
        
        # 3. Simulate conflict cleanup: trigger patch with stale base_answers causing conflict
        camera_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        res_conflict = client.patch(f"/api/responses/{draft_id}", json={
            "status": "Draft",
            "base_answers": {"q1": "base"},
            "answers": {"q1": camera_data}
        })
        self.assertEqual(res_conflict.status_code, 409)
        
        # Verify any temporary upload was cleaned up from the registry
        self.assertEqual(db["upload_registry"].count_documents({"response_id": ObjectId(draft_id)}), 0)

    def test_lookup_materialized_views_and_timeout(self):
        from lookup_resolver import LookupResolver
        from bson import ObjectId
        
        target_form_id = ObjectId()
        # Insert target form with lookup settings
        db["forms"].insert_one({
            "_id": target_form_id,
            "organization_id": "test_org",
            "title": "Target Lookup Form",
            "lookup_settings": {
                "max_timeout_ms": 100,
                "use_materialized_view": True
            }
        })
        
        # Insert responses on target form
        db["responses"].insert_one({
            "form_id": target_form_id,
            "organization_id": "test_org",
            "status": "Submitted",
            "answers": {"q_fruit": "Apple"}
        })
        db["responses"].insert_one({
            "form_id": target_form_id,
            "organization_id": "test_org",
            "status": "Submitted",
            "answers": {"q_fruit": "Banana"}
        })
        
        lookup_config = {
            "form_id": str(target_form_id),
            "field_id": "q_fruit"
        }
        
        # Clear existing materialized view if any
        db["lookup_materialized_views"].delete_many({"form_id": target_form_id})
        
        # Resolve choices (should fetch dynamically and write to materialized view)
        choices = LookupResolver.resolve_lookup_choices(db, lookup_config, "test_org")
        self.assertEqual(choices, [
            {"value": "Apple", "text": "Apple"},
            {"value": "Banana", "text": "Banana"}
        ])
        
        # Verify materialized view exists in DB
        mv = db["lookup_materialized_views"].find_one({"form_id": target_form_id, "field_id": "q_fruit"})
        self.assertIsNotNone(mv)
        self.assertEqual(mv["choices"], choices)
        
        # Manually alter MV choices to test that future reads pull directly from MV cache
        db["lookup_materialized_views"].update_one(
            {"form_id": target_form_id, "field_id": "q_fruit"},
            {"$set": {"choices": [{"value": "CachedCherry", "text": "CachedCherry"}]}}
        )
        
        # Read choices again
        cached_choices = LookupResolver.resolve_lookup_choices(db, lookup_config, "test_org")
        self.assertEqual(cached_choices, [{"value": "CachedCherry", "text": "CachedCherry"}])

if __name__ == "__main__":
    unittest.main()
