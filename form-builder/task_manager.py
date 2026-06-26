import time
import csv
import io
import threading
import logging
from bson import ObjectId
from datetime import datetime
from encryption_helper import EncryptionHelper
from anonymizer import DataAnonymizer
from s3_helper import S3Helper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TaskManager")

class TaskManager:
    @classmethod
    def create_export_task(cls, db, form, org_id, anonymize=False, user_id=None):
        """
        Creates a database task entry and spawns a background thread to execute it.
        """
        task_id = ObjectId()
        task_doc = {
            "_id": task_id,
            "form_id": form["_id"],
            "organization_id": org_id,
            "user_id": user_id,
            "status": "PENDING",
            "download_url": None,
            "error": None,
            "created_at": datetime.utcnow()
        }
        db["tasks"].insert_one(task_doc)

        thread = threading.Thread(target=cls._run_export_task, args=(db, task_id, form, org_id, anonymize, user_id))
        thread.start()

        return task_id

    @classmethod
    def _run_export_task(cls, db, task_id, form, org_id, anonymize, user_id):
        try:
            db["tasks"].update_one({"_id": task_id}, {"$set": {"status": "PROCESSING"}})
            logger.info(f"Processing export task {task_id}...")

            # 1. Fetch Responses
            form_id = form["_id"]
            responses = list(db["responses"].find({
                "form_id": form_id, 
                "organization_id": org_id,
                "status": "Submitted"
            }))

            # Extract fields/headers
            headers = ["response_id", "submitted_at"]
            sensitive_keys = []
            for v in form.get("versions", []):
                for sec in v.get("sections", []):
                    for q in sec.get("questions", []):
                        q_id = q.get("id")
                        if q_id not in headers:
                            headers.append(q_id)
                        if q.get("properties", {}).get("sensitive", False) and q_id not in sensitive_keys:
                            sensitive_keys.append(q_id)

            # 2. Write to CSV In-Memory Stream
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)

            for r in responses:
                answers = r.get("answers", {})
                
                # Decrypt PII fields
                if sensitive_keys:
                    answers = EncryptionHelper.process_sensitive_fields(answers, sensitive_keys, action="decrypt")
                    
                # Anonymize PII fields if requested
                if anonymize and sensitive_keys:
                    answers = DataAnonymizer.anonymize_answers(answers, sensitive_keys)

                row = [str(r["_id"]), r["submitted_at"].isoformat()]
                for h in headers[2:]:
                    row.append(str(answers.get(h, "")))
                writer.writerow(row)

            # 3. Upload file to S3
            filename = f"export_{form_id}_{int(time.time())}.csv"
            download_url = S3Helper.upload_file(
                output.getvalue().encode("utf-8"), 
                filename, 
                content_type="text/csv"
            )

            # Update status
            db["tasks"].update_one(
                {"_id": task_id}, 
                {"$set": {"status": "SUCCESS", "download_url": download_url}}
            )
            if user_id:
                try:
                    db["notifications"].insert_one({
                        "user_id": user_id,
                        "organization_id": org_id,
                        "title": "Export Completed",
                        "message": f"Your data export for form '{form.get('title')}' is ready for download.",
                        "type": "export_completed",
                        "read": False,
                        "created_at": datetime.utcnow(),
                        "details": {"task_id": str(task_id), "download_url": download_url}
                    })
                except Exception as ne:
                    logger.error(f"Failed to insert notification: {str(ne)}")
            logger.info(f"Export task {task_id} succeeded. File: {download_url}")
        
        except Exception as e:
            logger.error(f"Export task {task_id} failed: {str(e)}")
            db["tasks"].update_one(
                {"_id": task_id}, 
                {"$set": {"status": "FAILED", "error": str(e)}}
            )
