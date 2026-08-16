# pre-requisites: PGVector with schema created

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings
import psycopg
from pgvector.psycopg import register_vector
import hashlib
from psycopg.types.json import Json
import uuid
from pathlib import Path


load_dotenv()

CONNECTION_STRING = "postgresql://langchain:langchain@localhost:6024/langchain"

EMBEDDING_MODEL = HuggingFaceEndpointEmbeddings(
    model="Octen/Octen-Embedding-0.6B"
)


# Load the documents
file_path = (Path(__file__).parent/ "test_documents"/ "1810.04805v2.pdf")

loader = PyPDFLoader(file_path)

documents = loader.load()


# Chunking
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)

splitted_documents = splitter.split_documents(
    documents
)


for doc in splitted_documents[:5]:

    print("Content: ", doc.page_content)

    print("-" * 100)

    print("Metadata: ", doc.metadata)

    print("-" * 100)


# Embed the Document
texts = [
    doc.page_content
    for doc in splitted_documents
]

embeddings = EMBEDDING_MODEL.embed_documents(
    texts
)


# Hash function
def sha256_hash(text):

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# Generate a unique tenant ID
tenant_id = uuid.uuid4()


# Connect to PostgreSQL
conn = psycopg.connect(
    CONNECTION_STRING
)


with conn:

    register_vector(conn)

    with conn.cursor() as cur:

        for i, (doc, emb) in enumerate(
            zip(
                splitted_documents,
                embeddings
            )
        ):

            meta = doc.metadata or {}

            cur.execute(
                """
                INSERT INTO documents (
                    content,
                    embedding,
                    source_file,
                    page_number,
                    chunk_index,
                    total_chunks,
                    section_header,
                    doc_hash,
                    department,
                    access_level,
                    tenant_id,
                    created_by,
                    doc_type,
                    chunk_type,
                    extraction_method,
                    extraction_confidence,
                    chunk_length,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,

                (
                    doc.page_content,
                    emb,
                    meta.get("source"),
                    meta.get("page"),
                    i + 1,
                    120,
                    meta.get("section_header"),
                    sha256_hash(
                        doc.page_content
                    ),
                    "engineering",
                    "internal",
                    tenant_id,
                    "engineering_team@company.com",
                    "pdf",
                    "text",
                    "pypdf_extraction",
                    0.95,
                    len(doc.page_content),
                    Json(meta)
                ),
            )

        conn.commit()


print("Documents stored successfully")