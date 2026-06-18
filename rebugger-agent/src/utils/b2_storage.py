import boto3
from botocore.client import Config
import os
from src.core.config import settings
from src.utils.logger import get_logger

logger = get_logger("b2")

class B2Storage:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.B2_ENDPOINT,
            aws_access_key_id=settings.B2_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            config=Config(signature_version='s3v4')
        )
        self.bucket = settings.B2_BUCKET_NAME

    def upload_file(self, file_data, file_name, content_type='image/jpeg'):
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=file_name,
                Body=file_data,
                ContentType=content_type
            )
            url_host = settings.B2_ENDPOINT.replace("https://", "")
            return f"https://{self.bucket}.{url_host}/{file_name}"
        except Exception as e:
            logger.error("B2 upload failed", exc_info=True, extra={"data": {"file_name": file_name, "error": str(e)}})
            return None

b2_storage = B2Storage()
