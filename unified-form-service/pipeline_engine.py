import time
import json
import logging
import urllib.request
import threading
from datetime import datetime, timezone
from bson import ObjectId
from condition_evaluator import ConditionEvaluator

logger = logging.getLogger("PipelineEngine")

class PipelineEngine:
    @classmethod
    def execute_pipeline(cls, workflow, form_data, response_data, db=None):
        """
        Executes a workflow pipeline containing sequential/conditional steps.
        Uses a separate background thread.
        """
        def run():
            try:
                cls._run_workflow_steps(workflow, form_data, response_data, db)
            except Exception as e:
                logger.error(f"Pipeline workflow {workflow.get('id')} failed: {str(e)}")

        thread = threading.Thread(target=run)
        thread.start()

    @classmethod
    def _run_workflow_steps(cls, workflow, form_data, response_data, db):
        steps = workflow.get("steps", [])
        pipeline_run_id = str(ObjectId())
        
        logger.info(f"[PIPELINE RUN {pipeline_run_id}] Starting pipeline execution for form {form_data.get('_id')}")

        # Initialize workflow run tracker in MongoDB
        if db is not None:
            try:
                db["workflow_runs"].insert_one({
                    "_id": ObjectId(pipeline_run_id),
                    "form_id": ObjectId(form_data.get("_id")) if isinstance(form_data.get("_id"), (str, ObjectId)) else None,
                    "response_id": ObjectId(response_data.get("_id")) if isinstance(response_data.get("_id"), (str, ObjectId)) else None,
                    "workflow_id": workflow.get("id"),
                    "status": "RUNNING",
                    "steps": {},
                    "created_at": datetime.now(timezone.utc)
                })
            except Exception as e:
                logger.warning(f"Failed to initialize workflow run document: {str(e)}")

        # Shared execution variables context
        variables_context = {
            "form": {
                "id": str(form_data.get("_id")),
                "title": form_data.get("title")
            },
            "answers": response_data.get("answers", {}),
            "submitted_at": str(response_data.get("submitted_at")),
            "status": response_data.get("status"),
            "steps": {}
        }

        for step in steps:
            step_id = step.get("id")
            step_type = step.get("type")
            run_if = step.get("run_if")

            logger.info(f"[PIPELINE RUN {pipeline_run_id}] Preparing step '{step_id}' ({step_type})")

            # Check if this step should be skipped based on run_if rules
            if run_if:
                if not ConditionEvaluator.evaluate_rules(run_if, variables_context["answers"]):
                    logger.info(f"[PIPELINE RUN {pipeline_run_id}] Step '{step_id}' SKIPPED by condition.")
                    status_str = "SKIPPED"
                    output_data = {}
                    variables_context["steps"][step_id] = {"status": status_str, "output": output_data}
                    
                    if db is not None:
                        db["workflow_runs"].update_one(
                            {"_id": ObjectId(pipeline_run_id)},
                            {"$set": {f"steps.{step_id}": {"status": status_str, "output": output_data}}}
                        )
                    continue

            # Execute with Retries and exponential backoff
            max_retries = step.get("max_retries", 1)
            base_delay = step.get("retry_delay_seconds", 2)
            
            success = False
            output_data = {}
            
            for attempt in range(max_retries):
                logger.info(f"[PIPELINE RUN {pipeline_run_id}] Running step '{step_id}' - Attempt {attempt+1}/{max_retries}")
                
                try:
                    is_ok, res_data = cls._execute_step_action(step, variables_context, db)
                    if is_ok:
                        success = True
                        output_data = res_data
                        break
                except Exception as e:
                    logger.warning(f"Step '{step_id}' attempt {attempt+1} failed: {str(e)}")
                    output_data = {"error": str(e)}

                if attempt < max_retries - 1:
                    current_delay = base_delay * (2 ** attempt)
                    time.sleep(current_delay)

            status_str = "SUCCEEDED" if success else "FAILED"
            logger.info(f"[PIPELINE RUN {pipeline_run_id}] Step '{step_id}' finished with status: {status_str}")
            
            variables_context["steps"][step_id] = {
                "status": status_str,
                "output": output_data
            }

            # If failed, store details in failed_workflow_runs collection for forms creator review
            if not success:
                if db is not None:
                    try:
                        db["failed_workflow_runs"].insert_one({
                            "pipeline_run_id": ObjectId(pipeline_run_id),
                            "form_id": ObjectId(form_data.get("_id")) if isinstance(form_data.get("_id"), (str, ObjectId)) else None,
                            "workflow_id": workflow.get("id"),
                            "step_id": step_id,
                            "step_type": step_type,
                            "error": output_data.get("error", "Unknown error"),
                            "variables_context": variables_context,
                            "timestamp": datetime.now(timezone.utc)
                        })
                        org_id = form_data.get("organization_id")
                        db["notifications"].insert_one({
                            "organization_id": ObjectId(org_id) if isinstance(org_id, (str, ObjectId)) else None,
                            "title": "Workflow Step Failed",
                            "message": f"Step '{step_id}' failed in workflow '{workflow.get('id')}' for form '{form_data.get('title')}'",
                            "type": "workflow_failed",
                            "read": False,
                            "created_at": datetime.now(timezone.utc),
                            "details": {
                                "pipeline_run_id": str(pipeline_run_id),
                                "form_id": str(form_data.get("_id")),
                                "step_id": step_id,
                                "error": output_data.get("error", "Unknown error")
                            }
                        })
                    except Exception as ex:
                        logger.warning(f"Failed to record failed step or notification: {str(ex)}")

                # Execute fallback steps if defined
                fallback_steps = step.get("fallback_steps", [])
                if fallback_steps:
                    logger.info(f"[PIPELINE RUN {pipeline_run_id}] Running fallback steps for failed step '{step_id}'")
                    for fb_step in fallback_steps:
                        fb_id = fb_step.get("id")
                        fb_type = fb_step.get("type")
                        logger.info(f"[PIPELINE RUN {pipeline_run_id}] Running fallback step '{fb_id}' ({fb_type})")
                        try:
                            fb_ok, fb_res = cls._execute_step_action(fb_step, variables_context, db)
                            fb_status = "SUCCEEDED" if fb_ok else "FAILED"
                        except Exception as fb_err:
                            fb_status = "FAILED"
                            fb_res = {"error": str(fb_err)}
                        
                        variables_context["steps"][fb_id] = {
                            "status": fb_status,
                            "output": fb_res
                        }
                        if db is not None:
                            try:
                                db["workflow_runs"].update_one(
                                    {"_id": ObjectId(pipeline_run_id)},
                                    {"$set": {f"steps.{fb_id}": {"status": fb_status, "output": fb_res}}}
                                )
                            except Exception:
                                pass

            # Update step execution in MongoDB
            if db is not None:
                try:
                    db["workflow_runs"].update_one(
                        {"_id": ObjectId(pipeline_run_id)},
                        {
                            "$set": {
                                f"steps.{step_id}": {
                                    "status": status_str,
                                    "output": output_data
                                }
                            }
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to update step state in db: {str(e)}")

            if not success and step.get("critical", False):
                logger.error(f"[PIPELINE RUN {pipeline_run_id}] Critical step '{step_id}' failed. Halting pipeline.")
                break

        # Finalize run status in MongoDB
        final_status = "SUCCEEDED"
        for s_id, s_info in variables_context["steps"].items():
            if s_info["status"] == "FAILED":
                final_status = "FAILED"
                break

        if db is not None:
            try:
                db["workflow_runs"].update_one(
                    {"_id": ObjectId(pipeline_run_id)},
                    {"$set": {"status": final_status, "updated_at": datetime.now(timezone.utc)}}
                )
            except Exception as e:
                logger.warning(f"Failed to finalize workflow run document status: {str(e)}")

    @classmethod
    def _execute_step_action(cls, step, context, db):
        step_type = step.get("type")
        config = step.get("config", {})

        if step_type == "http_request":
            url = config.get("url")
            method = config.get("method", "POST")
            headers = config.get("headers", {})
            
            payload = {
                "form_id": context["form"]["id"],
                "answers": context["answers"],
                "status": context["status"]
            }
            
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, method=method)
            req.add_header("Content-Type", "application/json")
            for h_key, h_val in headers.items():
                req.add_header(h_key, h_val)

            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                try:
                    res_json = json.loads(res_body)
                except Exception:
                    res_json = {"raw": res_body}
                return (response.status >= 200 and response.status < 300), res_json

        elif step_type == "database_insert":
            collection_name = config.get("collection", "pipeline_logs")
            if db is not None:
                record = {
                    "timestamp": time.time(),
                    "form_id": context["form"]["id"],
                    "answers": context["answers"]
                }
                res = db[collection_name].insert_one(record)
                return True, {"inserted_id": str(res.inserted_id)}
            return False, {"error": "Database handle not available."}

        elif step_type == "email_simulator":
            to = config.get("to", "recipient@example.com")
            subject = config.get("subject", "Form Notification")
            logger.info(f"[EMAIL ENGINE] Dispatched email to {to} with subject '{subject}'")
            return True, {"status": "sent"}

        return False, {"error": f"Unknown step action: {step_type}"}
