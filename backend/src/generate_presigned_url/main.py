import json
import os
from datetime import datetime

import boto3
import shortuuid
from aws_lambda_powertools import Logger
from botocore.config import Config

DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
MEMORY_TABLE = os.environ["MEMORY_TABLE"]
BUCKET = os.environ["BUCKET"]
REGION = os.environ["REGION"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

ddb = boto3.resource("dynamodb")
document_table = ddb.Table(DOCUMENT_TABLE)
memory_table = ddb.Table(MEMORY_TABLE)
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    config=Config(
        s3={"addressing_style": "virtual"}, region_name=REGION, signature_version="s3v4"
    ),
)
logger = Logger()


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    file_name_full = event["queryStringParameters"]["file_name"]
    file_name = file_name_full.split(".pdf")[0]
    embed_model = event["queryStringParameters"].get(
        "embed_model", "amazon.titan-embed-text-v1"
    )
    llm_model = event["queryStringParameters"].get(
        "llm_model", "anthropic.claude-3-sonnet-20240229-v1:0"
    )

    logger.info(
        {
            "user_id": user_id,
            "file_name_full": file_name_full,
            "file_name": file_name,
            "embed_model": embed_model,
            "llm_model": llm_model,
        }
    )

    document_id = shortuuid.uuid()
    conversation_id = shortuuid.uuid()

    timestamp = datetime.utcnow()
    timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    key = f"{user_id}/{document_id}/{file_name}.pdf"

    document = {
        "userid": user_id,
        "documentid": document_id,
        "filename": file_name,
        "key": key,
        "created": timestamp_str,
        "docstatus": "UPLOADED",
        "conversations": [],
        "embed_model": embed_model,
        "llm_model": llm_model,
    }

    conversation = {"conversationid": conversation_id, "created": timestamp_str}
    document["conversations"].append(conversation)

    document_table.put_item(Item=document)

    conversation = {"SessionId": conversation_id, "History": []}
    memory_table.put_item(Item=conversation)

    presigned_url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": BUCKET,
            "Key": key,
            "ContentType": "application/pdf",
        },
        ExpiresIn=300,
        HttpMethod="PUT",
    )

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
        },
        "body": json.dumps({"presignedurl": presigned_url}),
    }
