"""Helper script to find and download the latest database backup from S3/MinIO.

Uses boto3 for bulletproof backup listing and downloading.
"""

from __future__ import annotations

import os
import sys
import boto3
from botocore.client import Config


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python download_latest_backup.py <destination_file_path>")
        sys.exit(1)

    dest_path = sys.argv[1]

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

    # List backups in the bucket
    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix="postgres/")
    except Exception as e:
        print(f"FATAL: Failed to list bucket contents: {e}")
        sys.exit(1)

    contents = response.get("Contents", [])
    if not contents:
        print(f"FATAL: No backups found in bucket '{bucket}' under 'postgres/'.")
        sys.exit(1)

    # Sort backups (newest first)
    contents.sort(key=lambda x: x["Key"], reverse=True)
    latest_key = contents[0]["Key"]

    s3.download_file(bucket, latest_key, dest_path)


if __name__ == "__main__":
    main()
