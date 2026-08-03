"""Contract test for S3/MinIO blob storage adapter.

Mark: pytest -m contract
"""

from __future__ import annotations

import hashlib

import pytest

from topos.adapters.blob.s3 import S3BlobStore
from topos.config import get_settings

pytestmark = pytest.mark.contract

# Same values the app connects with (from `.env` via get_settings()) rather
# than a second set of hardcoded defaults that can drift from it.
_settings = get_settings()
ENDPOINT = _settings.s3_endpoint
BUCKET = _settings.s3_bucket
ACCESS_KEY = _settings.s3_access_key
SECRET_KEY = _settings.s3_secret_key


@pytest.fixture
async def blob_store() -> S3BlobStore:
    store = S3BlobStore(
        endpoint_url=ENDPOINT,
        bucket=BUCKET,
        access_key_id=ACCESS_KEY,
        secret_access_key=SECRET_KEY,
    )
    # Ensure the bucket exists before testing
    async with await store._client() as s3:
        try:
            await s3.create_bucket(Bucket=BUCKET)
        except s3.exceptions.BucketAlreadyOwnedByYou:
            pass
        except s3.exceptions.BucketAlreadyExists:
            pass
    return store


@pytest.mark.asyncio
async def test_put_and_get_content_addressed(blob_store: S3BlobStore) -> None:
    data = b"Hello, Greek problem intelligence system!"
    expected_key = hashlib.sha256(data).hexdigest()

    # Put data
    key = await blob_store.put(key=None, data=data, content_type="text/plain")
    assert key == expected_key

    # Get data
    fetched = await blob_store.get(key)
    assert fetched == data


@pytest.mark.asyncio
async def test_put_with_custom_key(blob_store: S3BlobStore) -> None:
    data = b"custom key data"
    custom_key = "my-test-key-123"

    # Put data with custom key
    key = await blob_store.put(key=custom_key, data=data, content_type="text/plain")
    assert key == custom_key

    # Get data
    fetched = await blob_store.get(custom_key)
    assert fetched == data
