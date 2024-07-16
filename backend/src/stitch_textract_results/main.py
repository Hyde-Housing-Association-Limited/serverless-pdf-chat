import json
import os

import boto3
from aws_lambda_powertools import Logger
from fpdf import FPDF

DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
DOCUMENT_BUCKET = os.environ["DOCUMENT_BUCKET"]
QUEUE = os.environ["QUEUE"]

sqs = boto3.client("sqs")

s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
sfn = boto3.client("stepfunctions")

document_table = ddb.Table(DOCUMENT_TABLE)
logger = Logger()


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    print(event)
    document_id = event["documentid"]
    user_id = event["user"]
    key = event["key"]

    blocks = []
    client = boto3.client("textract")
    response = client.get_document_text_detection(JobId=event["JobId"], MaxResults=1000)
    blocks.append(response["Blocks"])
    while "NextToken" in response:
        response = client.get_document_text_detection(
            JobId=event["JobId"], NextToken=response["NextToken"], MaxResults=1000
        )
        blocks.append(response["Blocks"])

    full_output_path = f"/tmp/{event['JobId']}.pdf"
    sticth_textract_ouput(blocks, full_output_path)

    s3.upload_file(full_output_path, DOCUMENT_BUCKET, key)

    set_doc_status(user_id, document_id, "UPLOADED")

    # End the step function
    sfn.send_task_success(
        taskToken=event["TaskToken"],
        output=json.dumps({"documentid": document_id, "key": key, "user": user_id}),
    )

    # send message to sqs
    message = {
        "documentid": document_id,
        "key": key,
        "user": user_id,
    }
    sqs.send_message(QueueUrl=QUEUE, MessageBody=json.dumps(message))


def set_doc_status(user_id, document_id, status):
    document_table.update_item(
        Key={"userid": user_id, "documentid": document_id},
        UpdateExpression="SET docstatus = :docstatus",
        ExpressionAttributeValues={":docstatus": status},
    )


def sticth_textract_ouput(data, full_output_path):
    pages = {}
    for page_blocks in data:  # Iterate over each list (page) in data
        for block in page_blocks:  # Iterate over each block in the page
            if block["BlockType"] == "LINE":
                page_number = block["Page"]
                if page_number not in pages:
                    pages[page_number] = []
                pages[page_number].append(block["Text"])

    # Create a PDF document
    pdf = FPDF()
    pdf.set_font("Arial", size=10)

    # Sort pages by number and ensure pages without lines also get a PDF page
    max_page = max(pages.keys()) if pages else 0
    for page_number in range(1, max_page + 1):
        pdf.add_page()
        lines = pages.get(page_number, [])  # Handle pages that might not have any lines
        for line in lines:
            pdf.cell(200, 6, txt=line, ln=True)

    # Save the PDF document
    pdf.output(full_output_path)

    print("PDF created successfully with text.")
    return full_output_path


if __name__ == "__main__":
    event = {
        "TaskToken": "AQCUAAAAKgAAAAMAAAAAAAAAAbRs24OFtpyzRY26V+ByzNz0LoUBC/qCesyaey1MHg+ExI5caMYLKO5S9TqDxhG9KgFa2cXGFHPNJIXCV+uN83VAAszRatbcrm98xtJWzhygnKwogwjJ9ZFEffm+8C0=pBER6esx1RGLViBnB/TxQk7zOImqRDUlCrbw3+G8p4VEagJHEGbrELxRGJclowVGdtdLlpdmmQff6MtdhdwIxnLwqIYiNAaz/CXV7E8ALLoMi60vNTNCJo9+SGpMfYtD0X1Jpa8FoyDKd2rEBrG8ZaKkJBnQm8Y9f9Gj6JLaDL1Q8ZYRhl1LAihfDjU8d/+PgH4tzjBRE2i6n9Qo2B2qE3FvsidurBaPpKoYrEOOSqZJAaFUr6RqeJ3R9awEHi4l3BA6hNry8Mboo5lmOYlNk6ufTJFrvpKGobGyDwLKQUTmL2oe/blZ74yS5paeM0V4R6rh9A005nLEWSaFqS6sIYgCVLIBx/drgnL488EO56GaolYqWi9dygGr7C2DDN3udQweEPM35Ll6mKGRCe3cFib7S0yu/xtp3y6LVJOqhCgSAtCjmLvS+KQouwHi9mGkCwOrwYnYpnZQeoUn2kYLOgDC/0JoLu+zeNOW5aSLTcuT9aEaOuuI1uPxoR94Abgm4d2ipRWzHER2Xg05hHw6",
        "JobId": "853c664d22334dae1f4f95bbe89473edec8a8c447e4eb6087359d7d44b91ee8f",
    }
    lambda_handler(event, None)
