from __future__ import annotations

import os
import sys
import uuid

import boto3
import psycopg

database_url = os.environ["DATABASE_URL"]
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]

probe_id = "persistence-test-" + uuid.uuid4().hex
with psycopg.connect(database_url) as conn:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persistence_probe(
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("INSERT INTO persistence_probe(id) VALUES(%s)", (probe_id,))
    row = conn.execute("SELECT id FROM persistence_probe WHERE id=%s", (probe_id,)).fetchone()
    if not row:
        raise SystemExit("Databastest misslyckades.")
    conn.execute("DELETE FROM persistence_probe WHERE id=%s", (probe_id,))

if os.getenv("STORAGE_BACKEND", "local") == "s3":
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        region_name=os.getenv("S3_REGION", "eu-central-1"),
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    bucket = os.environ["S3_BUCKET"]
    key = f"projectmind/health/{probe_id}.txt"
    client.put_object(Bucket=bucket, Key=key, Body=b"ok", ServerSideEncryption="AES256")
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    client.delete_object(Bucket=bucket, Key=key)
    if body != b"ok":
        raise SystemExit("S3-test misslyckades.")

print("PostgreSQL och objektlagringen fungerar.")
