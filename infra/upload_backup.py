"""Helper script to upload database backups to S3/MinIO using boto3.

Works portably across platforms and manages full S3 signatures.
"""

from __future__ import annotations

import os
import sys
import boto3
from botocore.client import Config


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python upload_backup.py <file_path> <s3_key>")
        sys.exit(1)

    file_path = sys.argv[1]
    s3_key = sys.argv[2]

    # Resolve S3/MinIO credentials
    endpoint = os.environ.get("TOPOS_S3_ENDPOINT") or "http://localhost:9000"
    bucket = os.environ.get("TOPOS_S3_BUCKET") or "topos-backups"
    access_key = os.environ.get("S3_ACCESS_KEY") or "topos"
    secret_key = os.environ.get("S3_SECRET_KEY") or "devonlydevonly"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

    # Ensure bucket exists
    try:
        s3.create_bucket(Bucket=bucket)
    except Exception:
        pass

    s3.upload_file(file_path, bucket, s3_key)


if __name__ == "__main__":
    main()
