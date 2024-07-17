import json
import os
import urllib.parse

import boto3
import PyPDF2
from aws_lambda_powertools import Logger

DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
MEMORY_TABLE = os.environ["MEMORY_TABLE"]
QUEUE = os.environ["QUEUE"]
BUCKET = os.environ["BUCKET"]
STEP_FUNCTION = os.environ["STEP_FUNCTION"]


ddb = boto3.resource("dynamodb")
document_table = ddb.Table(DOCUMENT_TABLE)
memory_table = ddb.Table(MEMORY_TABLE)
sqs = boto3.client("sqs")
s3 = boto3.client("s3")
stef_func = boto3.client("stepfunctions")

logger = Logger()


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])
    split = key.split("/")
    user_id = split[0]
    document_id = split[1]
    file_name = split[2]

    logger.info({"key": key, "user_id": user_id, "document_id": document_id})

    s3.download_file(BUCKET, key, f"/tmp/{document_id}-{file_name}")

    with open(f"/tmp/{document_id}-{file_name}", "rb") as f:
        reader = PyPDF2.PdfReader(f)
        pages = str(len(reader.pages))

    filesize = (str(event["Records"][0]["s3"]["object"]["size"]),)

    document_table.update_item(
        Key={"userid": user_id, "documentid": document_id},
        UpdateExpression="SET filesize = :filesize",
        ExpressionAttributeValues={":filesize": filesize},
    )

    document_table.update_item(
        Key={"userid": user_id, "documentid": document_id},
        UpdateExpression="SET pages = :pages",
        ExpressionAttributeValues={":pages": pages},
    )

    message = {
        "documentid": document_id,
        "key": key,
        "user": user_id,
    }
    response = stef_func.start_execution(
        stateMachineArn=STEP_FUNCTION,
        input=json.dumps(message),
    )
    # sqs.send_message(QueueUrl=QUEUE, MessageBody=json.dumps(message))
