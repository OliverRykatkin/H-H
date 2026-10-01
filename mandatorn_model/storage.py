"""Tunn lagringsadapter mot ett S3-kompatibelt API (och en lokal katalog).

Inga AWS-specifika anrop får finnas utanför den här modulen. Byte av leverantör
(Bunny, Hetzner, R2) = ny endpoint och en annan invalidate-implementation.

Cache-policy sätts per objekt:
    put_immutable → Cache-Control: public, max-age=31536000, immutable
    put_pointer   → Cache-Control: public, s-maxage=5, max-age=0, no-cache
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

IMMUTABLE = "public, max-age=31536000, immutable"
POINTER = "public, s-maxage=5, max-age=0, no-cache"
ALIAS = "public, s-maxage=60, max-age=300"


class Storage(Protocol):
    def exists(self, key: str) -> bool: ...
    def get(self, key: str) -> bytes | None: ...
    def put_immutable(self, key: str, data: bytes, content_type: str, tags: dict | None = None) -> bool: ...
    def put_pointer(self, key: str, data: bytes, content_type: str, cache_control: str = POINTER) -> None: ...
    def list_releases(self) -> list[str]: ...
    def invalidate(self, paths: list[str]) -> None: ...


class LocalStorage:
    """Speglar bucket-strukturen i en katalog. Metadata i <nyckel>.meta.json."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.invalidated: list[str] = []

    def _path(self, key: str) -> Path:
        return self.root / key

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def _write(self, key: str, data: bytes, meta: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomärt byte inom samma filsystem
        p.with_name(p.name + ".meta.json").write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")

    def put_immutable(self, key: str, data: bytes, content_type: str, tags: dict | None = None) -> bool:
        if self.exists(key):
            return False
        self._write(key, data, {"ContentType": content_type, "CacheControl": IMMUTABLE, "Tags": tags or {}})
        return True

    def put_pointer(self, key: str, data: bytes, content_type: str, cache_control: str = POINTER) -> None:
        self._write(key, data, {"ContentType": content_type, "CacheControl": cache_control})

    def list_releases(self) -> list[str]:
        d = self.root / "releases"
        return sorted(p.name for p in d.iterdir() if (p / "manifest.json").exists()) if d.exists() else []

    def invalidate(self, paths: list[str]) -> None:
        self.invalidated.extend(paths)


class S3Storage:
    """S3-kompatibel lagring + valfri CloudFront-invalidering."""

    def __init__(self, bucket: str, endpoint_url: str | None = None, region: str = "eu-north-1",
                 distribution_id: str | None = None, client=None, cdn_client=None):
        import boto3  # importeras bara här

        self.bucket = bucket
        self.s3 = client or boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.distribution_id = distribution_id
        self._cdn = cdn_client
        if distribution_id and cdn_client is None:
            self._cdn = boto3.client("cloudfront")

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def put_immutable(self, key: str, data: bytes, content_type: str, tags: dict | None = None) -> bool:
        if self.exists(key):
            return False
        extra = {}
        if tags:
            from urllib.parse import urlencode

            extra["Tagging"] = urlencode(tags)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                           CacheControl=IMMUTABLE, **extra)
        return True

    def put_pointer(self, key: str, data: bytes, content_type: str, cache_control: str = POINTER) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                           CacheControl=cache_control)

    def list_releases(self) -> list[str]:
        out, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": "releases/", "Delimiter": "/"}
            if token:
                kw["ContinuationToken"] = token
            resp = self.s3.list_objects_v2(**kw)
            out += [cp["Prefix"].split("/")[1] for cp in resp.get("CommonPrefixes", [])]
            if not resp.get("IsTruncated"):
                return sorted(out)
            token = resp["NextContinuationToken"]

    def invalidate(self, paths: list[str]) -> None:
        if not (self.distribution_id and self._cdn and paths):
            return
        import time

        self._cdn.create_invalidation(
            DistributionId=self.distribution_id,
            InvalidationBatch={"Paths": {"Quantity": len(paths), "Items": ["/" + p.lstrip("/") for p in paths]},
                               "CallerReference": f"mandatorn-{time.time_ns()}"},
        )


def storage_from_uri(uri: str, distribution_id: str | None = None) -> Storage:
    """'s3://bucket' → S3Storage, annars en lokal katalog."""
    if uri.startswith("s3://"):
        return S3Storage(uri[5:].strip("/"), distribution_id=distribution_id)
    return LocalStorage(uri)
