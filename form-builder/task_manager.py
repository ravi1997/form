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

    @classmethod
    def run_upload_garbage_collector(cls, db):
        """
        Scans upload_registry, compares against active response references,
        deletes orphaned files from S3 and/or local storage, and clears registry entries.
        """
        logger.info("Starting upload registry garbage collection...")
        try:
            registry_entries = list(db["upload_registry"].find())
            responses = list(db["responses"].find({}, {"answers": 1}))
            active_urls = set()
            for r in responses:
                answers = r.get("answers", {})
                for key, val in answers.items():
                    if isinstance(val, str) and (val.startswith("/static/") or "s3" in val or "amazonaws.com" in val):
                        active_urls.add(val)
            
            deleted_count = 0
            for entry in registry_entries:
                file_path = entry["file_path"]
                from datetime import timedelta
                age = datetime.utcnow() - entry.get("created_at", datetime.utcnow())
                if file_path not in active_urls and age > timedelta(hours=1):
                    try:
                        if file_path.startswith("/static/"):
                            import os
                            local_path = file_path.replace("/static/", "static/")
                            if os.path.exists(local_path):
                                os.remove(local_path)
                        else:
                            S3Helper.delete_file(file_path)
                    except Exception as de:
                        logger.warning(f"Failed to delete orphaned file {file_path}: {str(de)}")
                    
                    db["upload_registry"].delete_one({"_id": entry["_id"]})
                    deleted_count += 1
            
            logger.info(f"Upload garbage collection completed. Cleaned up {deleted_count} files.")
            return deleted_count
        except Exception as e:
            logger.error(f"Upload garbage collection failed: {str(e)}")
            return 0

    @classmethod
    def run_local_to_s3_sync(cls, db):
        """
        Scans static/uploads/, uploads local files to S3, updates references in response answers,
        and registers the new S3 URLs in the upload_registry.
        """
        logger.info("Starting local-to-S3 sync...")
        import os
        upload_dir = "static/uploads"
        if not os.path.exists(upload_dir):
            return 0
            
        synced_count = 0
        try:
            for root, dirs, files in os.walk(upload_dir):
                for filename in files:
                    local_path = os.path.join(root, filename)
                    relative_url = f"/static/uploads/{filename}"
                    
                    try:
                        with open(local_path, "rb") as f:
                            file_data = f.read()
                        
                        s3_url = S3Helper.upload_file(file_data, filename)
                        if s3_url:
                            responses = list(db["responses"].find({}))
                            for r in responses:
                                updated_answers = {}
                                changed = False
                                for key, val in r.get("answers", {}).items():
                                    if val == relative_url:
                                        updated_answers[key] = s3_url
                                        changed = True
                                    else:
                                        updated_answers[key] = val
                                if changed:
                                    db["responses"].update_one(
                                        {"_id": r["_id"]},
                                        {"$set": {"answers": updated_answers}}
                                    )
                                    
                            db["upload_registry"].update_many(
                                {"file_path": relative_url},
                                {"$set": {"file_path": s3_url}}
                            )
                            
                            os.remove(local_path)
                            synced_count += 1
                    except Exception as ue:
                        logger.warning(f"Failed to sync {filename} to S3: {str(ue)}")
            
            logger.info(f"Local-to-S3 sync completed. Synced {synced_count} files.")
            return synced_count
        except Exception as e:
            logger.error(f"Local-to-S3 sync failed: {str(e)}")
            return 0
