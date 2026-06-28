import unittest
import sys
import os
import time
from flask import Flask, jsonify, request
from rate_limiter import rate_limit, in_memory_store

class RateLimiterTestCase(unittest.TestCase):
    def setUp(self):
        in_memory_store.clear()

    def test_rate_limiting_triggers_and_blocks(self):
        # We need to bypass the pytest check to actually test the rate limiting logic
        old_pytest = sys.modules.pop("pytest", None)
        os.environ["REQUIRE_AUTH"] = "true"
        
        try:
            app = Flask("test_rate_limit_app")
            app.config["AUTH_ENABLED"] = True
            app.config["REDIS_URL"] = None  # Force in-memory fallback

            @app.route("/test")
            @rate_limit(limit=2, period=2)
            def test_endpoint():
                return jsonify({"status": "ok"})

            with app.test_client() as client:
                # First request -> 200
                res1 = client.get("/test")
                self.assertEqual(res1.status_code, 200)

                # Second request -> 200
                res2 = client.get("/test")
                self.assertEqual(res2.status_code, 200)

                # Third request -> 429
                res3 = client.get("/test")
                self.assertEqual(res3.status_code, 429)
                self.assertEqual(res3.get_json()["status"], "error")
                self.assertIn("retry_after_seconds", res3.get_json())
                
        finally:
            if old_pytest is not None:
                sys.modules["pytest"] = old_pytest
            os.environ.pop("REQUIRE_AUTH", None)

if __name__ == "__main__":
    unittest.main()
