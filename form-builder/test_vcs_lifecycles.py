import unittest
import json
import os
from bson import ObjectId
from app import app, client, DB_NAME

class TestVCSLifecyclesAndWorkflows(unittest.TestCase):
    def setUp(self):
        os.environ["REQUIRE_AUTH"] = "true"
        self.client = app.test_client()

        # Clean collections
        client[DB_NAME]["users"].delete_many({})
        client[DB_NAME]["organizations"].delete_many({})
        client[DB_NAME]["projects"].delete_many({})
        client[DB_NAME]["forms"].delete_many({})
        client[DB_NAME]["workflow_runs"].delete_many({})

        # Setup test organization and user
        res = self.client.post("/api/auth/register", json={
            "email": "dev@company.com",
            "password": "devpassword123",
            "organization_name": "DevCorp"
        })
        reg_data = json.loads(res.data)
        self.token = reg_data["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

        # Create a base form
        res_form = self.client.post(
            "/api/forms",
            headers=self.auth_headers,
            json={
                "title": "VCS Form",
                "questions": [{"id": "q1", "type": "text", "title": "First Question"}]
            }
        )
        self.form_id = json.loads(res_form.data)["_id"]

    def tearDown(self):
        os.environ["REQUIRE_AUTH"] = "false"

    def test_git_commit_and_branches(self):
        # 1. Commit initial schema on 'main'
        sections_v1 = [{
            "id": "s1",
            "questions": [{"id": "q1", "type": "text", "title": "V1 Title"}]
        }]
        res_commit1 = self.client.post(
            f"/api/forms/{self.form_id}/commit",
            headers=self.auth_headers,
            json={"sections": sections_v1, "message": "Initial commit", "branch": "main"}
        )
        self.assertEqual(res_commit1.status_code, 201)
        commit1_hash = json.loads(res_commit1.data)["commit_hash"]
        self.assertIsNotNone(commit1_hash)

        # 2. Get commits history
        res_commits = self.client.get(f"/api/forms/{self.form_id}/commits", headers=self.auth_headers)
        self.assertEqual(res_commits.status_code, 200)
        commits_list = json.loads(res_commits.data)
        self.assertEqual(len(commits_list), 1)
        self.assertEqual(commits_list[0]["hash"], commit1_hash)

        # 3. Create branch 'feature-1' from 'main'
        res_branch = self.client.post(
            f"/api/forms/{self.form_id}/branches",
            headers=self.auth_headers,
            json={"branch_name": "feature-1", "source_branch": "main"}
        )
        self.assertEqual(res_branch.status_code, 201)

        # 4. Commit change to 'feature-1'
        sections_v2 = [{
            "id": "s1",
            "questions": [
                {"id": "q1", "type": "text", "title": "V1 Title"},
                {"id": "q2", "type": "number", "title": "Second Question"}
            ]
        }]
        res_commit2 = self.client.post(
            f"/api/forms/{self.form_id}/commit",
            headers=self.auth_headers,
            json={"sections": sections_v2, "message": "Add q2", "branch": "feature-1"}
        )
        commit2_hash = json.loads(res_commit2.data)["commit_hash"]

        # 5. Check Diff between main and feature-1
        res_diff = self.client.get(
            f"/api/forms/{self.form_id}/diff?from_ref=main&to_ref=feature-1",
            headers=self.auth_headers
        )
        self.assertEqual(res_diff.status_code, 200)
        diff_data = json.loads(res_diff.data)["diff"]
        self.assertEqual(len(diff_data["added"]), 1)
        self.assertEqual(diff_data["added"][0]["id"], "q2")

        # 6. Merge 'feature-1' into 'main'
        res_merge = self.client.post(
            f"/api/forms/{self.form_id}/merge",
            headers=self.auth_headers,
            json={"source_branch": "feature-1", "target_branch": "main"}
        )
        self.assertEqual(res_merge.status_code, 200)
        merge_data = json.loads(res_merge.data)
        self.assertTrue(merge_data["merged"])
        self.assertEqual(merge_data["type"], "fast_forward")

        # 7. Create tag 'v1.0'
        res_tag = self.client.post(
            f"/api/forms/{self.form_id}/tags",
            headers=self.auth_headers,
            json={"tag_name": "v1.0", "commit_hash": commit2_hash}
        )
        self.assertEqual(res_tag.status_code, 201)

        # List tags
        res_tags_list = self.client.get(f"/api/forms/{self.form_id}/tags", headers=self.auth_headers)
        self.assertEqual(res_tags_list.status_code, 200)
        tags = json.loads(res_tags_list.data)
        self.assertEqual(tags.get("v1.0"), commit2_hash)

        # 8. Revert 'main' to 'Initial commit' (commit1_hash)
        res_revert = self.client.post(
            f"/api/forms/{self.form_id}/revert",
            headers=self.auth_headers,
            json={"commit_hash": commit1_hash, "branch": "main"}
        )
        self.assertEqual(res_revert.status_code, 200)

    def test_lifecycles(self):
        # 1. Form Lifecycle
        res_form_lc = self.client.patch(
            f"/api/forms/{self.form_id}/lifecycle",
            headers=self.auth_headers,
            json={"lifecycle": "Paused"}
        )
        self.assertEqual(res_form_lc.status_code, 200)

        db_form = client[DB_NAME]["forms"].find_one({"_id": ObjectId(self.form_id)})
        self.assertEqual(db_form.get("lifecycle"), "Paused")

        # 2. Org Lifecycle
        res_org_lc = self.client.patch(
            "/api/org/lifecycle",
            headers=self.auth_headers,
            json={"lifecycle": "Trial"}
        )
        self.assertEqual(res_org_lc.status_code, 200)

    def test_workflows_history_and_runs(self):
        # Create a form with a sample pipeline workflow configured
        workflow_payload = {
            "title": "Pipeline Workflow Form",
            "workflows": [
                {
                    "id": "on_submit_pipeline",
                    "trigger": "on_submit",
                    "steps": [
                        {
                            "id": "dispatch_simulator",
                            "type": "email_simulator",
                            "config": {"to": "support@company.com", "subject": "Notification Alert"}
                        }
                    ]
                }
            ],
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q1", "type": "text", "required": True}]
                }
            ]
        }
        res_form = self.client.post("/api/forms", headers=self.auth_headers, json=workflow_payload)
        wf_form_id = json.loads(res_form.data)["_id"]

        # 1. Submit response (triggers the workflow asynchronously)
        res_submit = self.client.post(
            f"/api/forms/{wf_form_id}/submit",
            headers=self.auth_headers,
            json={"q1": "Workflows rock!"}
        )
        self.assertEqual(res_submit.status_code, 201)

        # Wait a brief moment for the thread to process and save the log
        import time
        time.sleep(0.5)

        # 2. Fetch Workflow runs for this form
        res_runs = self.client.get(
            f"/api/forms/{wf_form_id}/workflows/runs",
            headers=self.auth_headers
        )
        self.assertEqual(res_runs.status_code, 200)
        runs = json.loads(res_runs.data)
        self.assertTrue(len(runs) >= 1)
        self.assertEqual(runs[0]["status"], "SUCCEEDED")
        self.assertIn("dispatch_simulator", runs[0]["steps"])
        self.assertEqual(runs[0]["steps"]["dispatch_simulator"]["status"], "SUCCEEDED")

    def test_git_purge_and_keep(self):
        # Create a commit
        res_commit = self.client.post(
            f"/api/forms/{self.form_id}/commit",
            headers=self.auth_headers,
            json={"sections": [{"id": "s1", "questions": []}], "message": "Purge Test Commit", "branch": "main"}
        )
        self.assertEqual(res_commit.status_code, 201)
        commit_hash = json.loads(res_commit.data)["commit_hash"]

        # Mark to keep
        res_keep = self.client.patch(
            f"/api/forms/{self.form_id}/commits/{commit_hash}/keep",
            headers=self.auth_headers,
            json={"keep": True}
        )
        self.assertEqual(res_keep.status_code, 200)

        # Trigger purge
        res_purge = self.client.post(
            f"/api/forms/{self.form_id}/commits/purge",
            headers=self.auth_headers
        )
        self.assertEqual(res_purge.status_code, 200)

    def test_responses_and_notifications(self):
        # 1. Post a response
        res_sub = self.client.post(
            f"/api/forms/{self.form_id}/submit",
            headers=self.auth_headers,
            json={"q1": "Response content"}
        )
        self.assertEqual(res_sub.status_code, 201)
        resp_id = json.loads(res_sub.data)["response"]["_id"]

        # 2. Get the response
        res_get = self.client.get(
            f"/api/responses/{resp_id}",
            headers=self.auth_headers
        )
        self.assertEqual(res_get.status_code, 200)
        resp_data = json.loads(res_get.data)
        self.assertEqual(resp_data["answers"]["q1"], "Response content")

        # 3. Get all responses of a form
        res_all = self.client.get(
            f"/api/forms/{self.form_id}/responses",
            headers=self.auth_headers
        )
        self.assertEqual(res_all.status_code, 200)
        self.assertTrue(len(json.loads(res_all.data)) >= 1)

        # 4. Check notifications polling route
        res_notif = self.client.get(
            "/api/notifications",
            headers=self.auth_headers
        )
        self.assertEqual(res_notif.status_code, 200)

if __name__ == "__main__":
    unittest.main()
