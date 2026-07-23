"""Content-addressed S3/MinIO blob store.

Implements service.ports.BlobStore Protocol. Uses aioboto3.
See ARCHITECTURE.md > Data access and > Repository layout.
"""

from __future__ import annotations

import hashlib
import typing

import aioboto3
from botocore.config import Config as BotoConfig


class S3BlobStore:
    """Content-addressed blob storage backed by S3 or MinIO.

    Keys are the lowercase hex sha256 of the stored data (content-addressed).
    The key is returned from put() so callers can record it.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._endpoint = endpoint_url
        self._bucket = bucket
        self._access_key = access_key_id
        self._secret_key = secret_access_key
        self._config = BotoConfig(retries={"max_attempts": 3, "mode": "adaptive"})

    async def _client(self) -> typing.Any:
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=self._config,
        )

    async def put(
        self,
        key: str | None = None,
        data: bytes = b"",
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store data, returning its content-addressed sha256 key.

        If *key* is None it is computed as sha256 hexdigest of *data*.
        """
        actual_key = key or hashlib.sha256(data).hexdigest()
        async with await self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=actual_key,
                Body=data,
                ContentType=content_type,
            )
        return actual_key

    async def get(self, key: str) -> bytes:
        """Retrieve data by its content-addressed key."""
        async with await self._client() as s3:
            obj = await s3.get_object(Bucket=self._bucket, Key=key)
            async with obj["Body"] as stream:
                return await stream.read()  # type: ignore[no-any-return]
