import io

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.config import settings


def get_s3_client() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def ensure_bucket() -> None:
    client = get_s3_client()

    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")

        if error_code not in {"404", "NoSuchBucket", "NotFound"}:
            raise

        client.create_bucket(Bucket=settings.s3_bucket)


def upload_file(
    file_bytes: bytes,
    storage_key: str,
    content_type: str,
) -> str:
    ensure_bucket()
    client = get_s3_client()

    client.upload_fileobj(
        io.BytesIO(file_bytes),
        settings.s3_bucket,
        storage_key,
        ExtraArgs={"ContentType": content_type},
    )

    return storage_key


def delete_file(storage_key: str) -> None:
    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket, Key=storage_key)


def download_file(storage_key: str) -> bytes:
    client = get_s3_client()

    response = client.get_object(
        Bucket=settings.s3_bucket,
        Key=storage_key,
    )

    try:
        return response["Body"].read()
    finally:
        response["Body"].close()
