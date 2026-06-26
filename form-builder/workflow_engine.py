import logging
import urllib.request
import json
import threading
from script_sandbox import ScriptSandbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WorkflowEngine")

class WorkflowEngine:
    @staticmethod
    def execute_webhook(url, method, payload):
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, 
                data=data, 
                headers={"Content-Type": "application/json"},
                method=method.upper()
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                logger.info(f"Pipeline Webhook to {url} returned status: {response.status}")
        except Exception as e:
            logger.error(f"Pipeline Webhook to {url} failed: {str(e)}")

    @classmethod
    def execute_pipeline(cls, workflow, payload):
        """
        Executes a sequence of steps defined inside a workflow configuration.
        """
        steps = workflow.get("steps", [])
        logger.info(f"Executing pipeline workflow '{workflow.get('id')}' containing {len(steps)} steps.")
        
        for idx, step in enumerate(steps):
            step_type = step.get("type")
            logger.info(f"Running step {idx+1}: {step_type}")
            
            if step_type == "webhook":
                url = step.get("url")
                method = step.get("method", "POST")
                if url:
                    cls.execute_webhook(url, method, payload)
            
            elif step_type == "email_simulator":
                to = step.get("to", "recipient@example.com")
                subject = step.get("subject", "Notification")
                logger.info(f"[EMAIL SIMULATOR] Sending email to {to} | Subject: '{subject}' | Answers count: {len(payload.get('answers', {}))}")
            
            elif step_type == "script":
                script_body = step.get("script")
                if script_body:
                    is_ok, err_msg = ScriptSandbox.execute_script(script_body, payload.get("answers", {}))
                    logger.info(f"[SCRIPT ACTION] Executed custom script. Result: {is_ok}, Output: {err_msg}")
                    if not is_ok:
                        logger.warning(f"Pipeline step halted due to script evaluation failure: {err_msg}")
                        break

    @classmethod
    def trigger_workflows(cls, workflows, form_data, response_data):
        """
        Launches workflow pipeline threads.
        """
        if not workflows:
            return

        payload = {
            "form_id": str(form_data.get("_id")),
            "title": form_data.get("title"),
            "submitted_at": response_data.get("submitted_at").isoformat() if hasattr(response_data.get("submitted_at"), "isoformat") else str(response_data.get("submitted_at")),
            "answers": response_data.get("answers", {}),
            "status": response_data.get("status", "Submitted")
        }

        for wf in workflows:
            trigger = wf.get("trigger", "on_submit")
            if trigger == "on_submit":
                thread = threading.Thread(target=cls.execute_pipeline, args=(wf, payload))
                thread.start()
