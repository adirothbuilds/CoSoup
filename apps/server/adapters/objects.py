import hashlib
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ..config import secret_file
from ..errors import ServiceError


class R2ObjectStore:
    durable = True

    def __init__(self, settings):
        if not settings.r2_endpoint or not settings.r2_bucket:
            raise ServiceError("archive_not_connected", "Configure a private R2 endpoint, bucket and credential files before archiving")
        self.bucket = settings.r2_bucket
        self.client = boto3.client("s3", endpoint_url=settings.r2_endpoint, region_name="auto",
                                   aws_access_key_id=secret_file(settings.r2_access_key_file),
                                   aws_secret_access_key=secret_file(settings.r2_secret_key_file),
                                   config=Config(retries={"total_max_attempts": 1}, connect_timeout=15, read_timeout=60))

    def put(self, key, source):
        try:
            self.client.upload_file(str(source), self.bucket, key)
        except (ClientError, BotoCoreError):
            raise ServiceError("archive_upload_failed", "R2 upload failed; local originals are retained") from None

    def download(self, key, destination, max_bytes):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            if response["ContentLength"] > max_bytes:
                response["Body"].close()
                raise ServiceError("archive_size_limit", "Remote archive exceeds configured restore limit")
            count = 0
            with Path(destination).open("wb") as f, response["Body"] as body:
                while chunk := body.read(1024*1024):
                    count += len(chunk)
                    if count > max_bytes:
                        raise ServiceError("archive_size_limit", "Remote archive exceeds configured restore limit")
                    f.write(chunk)
        except (ClientError, BotoCoreError):
            raise ServiceError("archive_download_failed", "R2 download failed; no local originals were removed") from None

    def verify(self, key, digest, size):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            h, count = hashlib.sha256(), 0
            with response["Body"] as body:
                while chunk := body.read(1024*1024):
                    count += len(chunk)
                    if count > size:
                        raise ServiceError("archive_integrity", "Remote object length does not match")
                    h.update(chunk)
            if count != size or h.hexdigest() != digest:
                raise ServiceError("archive_integrity", "Remote object failed full read/hash validation")
        except (ClientError, BotoCoreError):
            raise ServiceError("archive_verify_failed", "R2 read verification failed; local originals are retained") from None
