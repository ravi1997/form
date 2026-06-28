import os
import boto3
import uuid
import logging
from botocore.client import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("S3Helper")

# Configs
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") # E.g., http://localhost:9000 for MinIO
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "form-uploads")
S3_REGION_NAME = os.getenv("S3_REGION_NAME", "us-east-1")

class S3Helper:
    _client = None

    @classmethod
    def get_client(cls):
        if not S3_ACCESS_KEY or not S3_SECRET_KEY:
            # No credentials supplied, operate in Local Fallback mode (useful for local test runs)
            return None

        if cls._client is None:
            params = {
                "aws_access_key_id": S3_ACCESS_KEY,
                "aws_secret_access_key": S3_SECRET_KEY,
                "region_name": S3_REGION_NAME,
                "config": Config(signature_version="s3v4")
            }
            if S3_ENDPOINT_URL:
                params["endpoint_url"] = S3_ENDPOINT_URL
                params["config"] = Config(signature_version="s3v4", s3={"addressing_style": "path"})
                
            cls._client = boto3.client("s3", **params)
            cls._ensure_bucket_exists()
        return cls._client

    @classmethod
    def _ensure_bucket_exists(cls):
        client = cls._client
        try:
            client.head_bucket(Bucket=S3_BUCKET_NAME)
        except Exception:
            logger.info(f"Bucket '{S3_BUCKET_NAME}' does not exist. Creating it...")
            try:
                if S3_ENDPOINT_URL:
                    client.create_bucket(Bucket=S3_BUCKET_NAME)
                else:
                    if S3_REGION_NAME == "us-east-1":
                        client.create_bucket(Bucket=S3_BUCKET_NAME)
                    else:
                        client.create_bucket(
                            Bucket=S3_BUCKET_NAME,
                            CreateBucketConfiguration={"LocationConstraint": S3_REGION_NAME}
                        )
                # Set public read policy
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "PublicRead",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{S3_BUCKET_NAME}/*"]
                        }
                    ]
                }
                import json
                client.put_bucket_policy(Bucket=S3_BUCKET_NAME, Policy=json.dumps(policy))
            except Exception as e:
                logger.warning(f"Could not auto-create S3 bucket or set policy: {str(e)}")

    @classmethod
    def upload_file(cls, file_bytes, filename, content_type="application/octet-stream"):
        client = cls.get_client()
        if client is None:
            # --- Local Fallback Mode ---
            upload_dir = "static/uploads"
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as fh:
                fh.write(file_bytes)
            logger.info(f"Local storage fallback upload: {filepath}")
            return f"/static/uploads/{filename}"

        try:
            client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=filename,
                Body=file_bytes,
                ContentType=content_type
            )
            if S3_ENDPOINT_URL:
                return f"{S3_ENDPOINT_URL}/{S3_BUCKET_NAME}/{filename}"
            else:
                return f"https://{S3_BUCKET_NAME}.s3.{S3_REGION_NAME}.amazonaws.com/{filename}"
        except Exception as e:
            logger.error(f"Failed to upload to S3: {str(e)}")
            raise ValueError(f"S3 Object Storage Upload failed: {str(e)}")

    @classmethod
    def delete_file(cls, filepath):
        if not filepath:
            return
        if filepath.startswith("/static/uploads/"):
            local_path = filepath.lstrip("/")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                    logger.info(f"Locally deleted file: {local_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete local file {local_path}: {str(e)}")
            return

        client = cls.get_client()
        if client is None:
            # Maybe local file fallback
            filename = filepath.split("/")[-1]
            local_path = os.path.join("static/uploads", filename)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
            return

        try:
            filename = filepath.split("/")[-1]
            client.delete_object(Bucket=S3_BUCKET_NAME, Key=filename)
            logger.info(f"Deleted S3 object: {filename}")
        except Exception as e:
            logger.error(f"Failed to delete S3 object {filepath}: {str(e)}")
