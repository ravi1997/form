import unittest
import json
import os
from bson import ObjectId
from app import app, client, DB_NAME
from auth import AuthManager

class TestAuthAndACL(unittest.TestCase):
    def setUp(self):
        # Enforce authentication requirement for these security integration tests
        os.environ["REQUIRE_AUTH"] = "true"
        self.client = app.test_client()
        
        # Clean users and organizations
        client[DB_NAME]["users"].delete_many({})
        client[DB_NAME]["organizations"].delete_many({})
        client[DB_NAME]["projects"].delete_many({})
        client[DB_NAME]["forms"].delete_many({})

    def tearDown(self):
        os.environ["REQUIRE_AUTH"] = "false"

    def test_user_registration_and_login_flow(self):
        # 1. Register a new user & org
        reg_payload = {
            "email": "owner@company.com",
            "password": "securepassword123",
            "first_name": "Alice",
            "last_name": "Smith",
            "organization_name": "Alice Industries",
            "allowed_email_domains": ["company.com"]
        }
        res_reg = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(res_reg.status_code, 201)
        
        reg_data = json.loads(res_reg.data)
        self.assertIn("access_token", reg_data)
        self.assertEqual(reg_data["user"]["email"], "owner@company.com")
        self.assertEqual(reg_data["user"]["roles"], ["Admin"])
        self.assertEqual(reg_data["organization"]["name"], "Alice Industries")
        
        # Save token for next tests
        access_token = reg_data["access_token"]
        refresh_token = reg_data["refresh_token"]

        # 2. Try registering duplicate email
        res_dup = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn("error", json.loads(res_dup.data))

        # 3. Log in with the registered credentials
        login_payload = {
            "email": "owner@company.com",
            "password": "securepassword123"
        }
        res_login = self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(res_login.status_code, 200)
        
        login_data = json.loads(res_login.data)
        self.assertIn("access_token", login_data)
        self.assertEqual(login_data["user"]["first_name"], "Alice")

        # 4. Refresh token validation
        res_refresh = self.client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        self.assertEqual(res_refresh.status_code, 200)
        self.assertIn("access_token", json.loads(res_refresh.data))

        # 5. Reset password check
        reset_payload = {
            "email": "owner@company.com",
            "new_password": "brandnewpassword999"
        }
        res_reset = self.client.post("/api/auth/reset-password", json=reset_payload)
        self.assertEqual(res_reset.status_code, 200)

        # Login with old password should fail now
        res_fail_login = self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(res_fail_login.status_code, 401)

    def test_acl_workspace_and_form_sharing(self):
        # 1. Register Owner (Admin) and Guest (will become Analyst)
        res_owner = self.client.post("/api/auth/register", json={
            "email": "admin@company.com",
            "password": "adminpwd123",
            "organization_name": "ShareOrg"
        })
        owner_data = json.loads(res_owner.data)
        owner_token = owner_data["access_token"]
        org_id = owner_data["organization"]["id"]

        # Register secondary user under the same organization
        # To register under same org, we can use org user addition endpoint with Owner's token!
        res_add_guest = self.client.post(
            "/api/org/users",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "email": "analyst@company.com",
                "password": "analystpwd123",
                "first_name": "Bob",
                "roles": ["Respondent"] # Starts as basic respondent
            }
        )
        self.assertEqual(res_add_guest.status_code, 201)

        # Log in guest to get token
        res_guest_login = self.client.post("/api/auth/login", json={
            "email": "analyst@company.com",
            "password": "analystpwd123"
        })
        guest_data = json.loads(res_guest_login.data)
        guest_token = guest_data["access_token"]
        guest_id = guest_data["user"]["id"]

        # 2. Owner creates a Project
        res_proj = self.client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Confidential Project"}
        )
        proj_id = json.loads(res_proj.data)["_id"]

        # 3. Guest tries to get the Project - Access Denied (Respondent role defaults to no project access)
        res_get_fail = self.client.get(
            f"/api/projects/{proj_id}",
            headers={"Authorization": f"Bearer {guest_token}"}
        )
        self.assertEqual(res_get_fail.status_code, 403)

        # 4. Owner shares the Project with Guest as Analyst
        res_share = self.client.post(
            f"/api/projects/{proj_id}/share",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"email": "analyst@company.com", "role": "Analyst"}
        )
        self.assertEqual(res_share.status_code, 200)

        # 5. Guest tries again to get Project - Success!
        res_get_ok = self.client.get(
            f"/api/projects/{proj_id}",
            headers={"Authorization": f"Bearer {guest_token}"}
        )
        self.assertEqual(res_get_ok.status_code, 200)

        # 6. Guest tries to delete the Project - Access Denied (Analyst can't delete)
        res_del_fail = self.client.delete(
            f"/api/projects/{proj_id}",
            headers={"Authorization": f"Bearer {guest_token}"}
        )
        self.assertEqual(res_del_fail.status_code, 403)

    def test_tenant_db_isolation(self):
        # Enable physical tenant separation flag
        os.environ["TENANT_DB_ISOLATION"] = "true"

        # Register User A (Org A)
        res_a = self.client.post("/api/auth/register", json={
            "email": "userA@a.com",
            "password": "pwdA",
            "organization_name": "OrgA"
        })
        token_a = json.loads(res_a.data)["access_token"]
        org_a_id = json.loads(res_a.data)["organization"]["id"]

        # Register User B (Org B)
        res_b = self.client.post("/api/auth/register", json={
            "email": "userB@b.com",
            "password": "pwdB",
            "organization_name": "OrgB"
        })
        token_b = json.loads(res_b.data)["access_token"]
        org_b_id = json.loads(res_b.data)["organization"]["id"]

        # User A creates a form
        res_form_a = self.client.post(
            "/api/forms",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"title": "Form in Tenant A", "questions": [{"id": "q1", "type": "text"}]}
        )
        form_a_id = json.loads(res_form_a.data)["_id"]

        # Check database isolation: form_a should be inside org A's database
        db_a_name = f"form_db_{org_a_id}"
        db_b_name = f"form_db_{org_b_id}"
        
        self.assertIsNotNone(client[db_a_name]["forms"].find_one({"_id": ObjectId(form_a_id)}))
        self.assertIsNone(client[db_b_name]["forms"].find_one({"_id": ObjectId(form_a_id)}))

        # Reset Tenant isolation env variable
        os.environ["TENANT_DB_ISOLATION"] = "false"

if __name__ == "__main__":
    unittest.main()
