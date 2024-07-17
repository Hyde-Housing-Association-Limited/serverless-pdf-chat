import json
import os

import boto3
from aws_lambda_powertools import Logger
from langchain.chains import ConversationalRetrievalChain
from langchain.embeddings import BedrockEmbeddings
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_message_histories import DynamoDBChatMessageHistory
from langchain.vectorstores import FAISS
from langchain_community.chat_models import BedrockChat

MEMORY_TABLE = os.environ["MEMORY_TABLE"]
DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
BUCKET = os.environ["BUCKET"]
MODEL_ID = os.environ["MODEL_ID"]

s3 = boto3.client("s3")
logger = Logger()


def get_embeddings(embeddings_model):
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name="us-east-1",
    )

    embeddings = BedrockEmbeddings(
        model_id=embeddings_model,
        client=bedrock_runtime,
        region_name="us-east-1",
    )
    return embeddings


def get_faiss_index(embeddings, user, document_id):
    s3.download_file(BUCKET, f"{user}/{document_id}/index.faiss", "/tmp/index.faiss")
    s3.download_file(BUCKET, f"{user}/{document_id}/index.pkl", "/tmp/index.pkl")
    faiss_index = FAISS.load_local(
        "/tmp", embeddings, allow_dangerous_deserialization=True
    )
    return faiss_index


def create_memory(conversation_id):
    message_history = DynamoDBChatMessageHistory(
        table_name=MEMORY_TABLE, session_id=conversation_id
    )

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        chat_memory=message_history,
        input_key="question",
        output_key="answer",
        return_messages=True,
    )
    return memory


def bedrock_chain(
    faiss_index,
    memory,
    human_input,
    bedrock_runtime,
    llm_model=MODEL_ID,
    temperature=0.0,
):

    chat = BedrockChat(model_id=llm_model, model_kwargs={"temperature": temperature})

    chain = ConversationalRetrievalChain.from_llm(
        llm=chat,
        chain_type="stuff",
        retriever=faiss_index.as_retriever(),
        memory=memory,
        return_source_documents=True,
    )

    response = chain.invoke({"question": human_input})

    return response


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context):
    event_body = json.loads(event["body"])
    file_name = event_body["fileName"]
    human_input = event_body["prompt"]
    document_id = event_body["documentId"]
    conversation_id = event["pathParameters"]["conversationid"]
    user = event["requestContext"]["authorizer"]["claims"]["sub"]
    embeddings_model = event_body["embeddings_model"]
    llm_model = event_body["llm_model"]
    temperature = event_body.get("temp", 0.5)

    logger.info(
        {
            "user": user,
            "conversation_id": conversation_id,
            "human_input": human_input,
            "file_name": file_name,
            "embeddings_model": embeddings_model,
            "llm_model": llm_model,
            "temp": temperature,
        }
    )

    embeddings = get_embeddings(embeddings_model)
    faiss_index = get_faiss_index(embeddings, user, document_id)
    memory = create_memory(conversation_id)
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name="eu-central-1",
    )

    response = bedrock_chain(
        faiss_index, memory, human_input, bedrock_runtime, llm_model, temperature
    )
    if response:
        print(f"{llm_model} -\nPrompt: {human_input}\n\nResponse: {response['answer']}")
    else:
        raise ValueError(f"Unsupported model ID: {llm_model}")

    logger.info(str(response["answer"]))

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
        },
        "body": json.dumps(response["answer"]),
    }
