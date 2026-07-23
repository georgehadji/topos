"""Contract test: S3BlobStore against the docker-compose MinIO.

Requires the docker-compose stack running (`docker compose up -d`).
Mark: pytest -m contract
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess

import aioboto3
import botocore
import pytest

from topos.adapters.blob.s3 import S3BlobStore

pytestmark = pytest.mark.contract


def _find_minio_host() -> str:
    """Find the IP where minio is reachable (WSL2 or localhost)."""
    try:
        result = subprocess.run(
            ["wsl", "--", "ip", "-4", "addr", "show", "eth0"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        for line in result.stdout.splitlines():
            if "inet " in line:
                ip = line.strip().split()[1].split("/")[0]
                s = socket.socket()
                s.settimeout(1)
                try:
                    s.connect((ip, 9000))
                    s.close()
                    return ip
                except (OSError, TimeoutError):
                    pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    host = os.environ.get("TOPOS_TEST_MINIO_HOST")
    if host:
        return host

    return "127.0.0.1"


HOST = _find_minio_host()
ENDPOINT = f"http://{HOST}:9000"
BUCKET = "topos-test-blob"


@pytest.fixture(autouse=True)
async def _ensure_bucket() -> None:
    """Create the test bucket if it doesn't exist."""
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id="topos",
        aws_secret_access_key="devonlydevonly",
    ) as s3:
        existing = [b["Name"] for b in (await s3.list_buckets())["Buckets"]]
        if BUCKET not in existing:
            await s3.create_bucket(Bucket=BUCKET)


@pytest.fixture
def store() -> S3BlobStore:
    return S3BlobStore(
        endpoint_url=ENDPOINT,
        bucket=BUCKET,
        access_key_id="topos",
        secret_access_key="devonlydevonly",
    )


@pytest.mark.asyncio
async def test_put_and_get(store: S3BlobStore) -> None:
    data = b"hello this is a test document"
    key = await store.put(data=data, content_type="text/plain")
    assert isinstance(key, str)
    assert len(key) == 64  # sha256 hex

    got = await store.get(key)
    assert got == data


@pytest.mark.asyncio
async def test_content_addressed_dedup(store: S3BlobStore) -> None:
    """Same content produces the same key."""
    data = b"exact same content"
    key1 = await store.put(data=data, content_type="text/plain")
    key2 = await store.put(data=data, content_type="text/plain")
    assert key1 == key2


@pytest.mark.asyncio
async def test_different_content_different_key(store: S3BlobStore) -> None:
    k1 = await store.put(data=b"content a", content_type="text/plain")
    k2 = await store.put(data=b"content b", content_type="text/plain")
    assert k1 != k2


@pytest.mark.asyncio
async def test_put_with_explicit_key(store: S3BlobStore) -> None:
    data = b"explicit key data"
    expected_key = hashlib.sha256(data).hexdigest()
    key = await store.put(key=expected_key, data=data, content_type="text/plain")
    assert key == expected_key

    got = await store.get(key)
    assert got == data


@pytest.mark.asyncio
async def test_get_nonexistent_key_raises(store: S3BlobStore) -> None:
    with pytest.raises(botocore.exceptions.ClientError):
        await store.get("nonexistent-key-that-should-not-exist-12345678")
