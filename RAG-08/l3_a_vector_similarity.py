from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEndpointEmbeddings

import hashlib
import datetime
import numpy as np

from dotenv import load_dotenv


# ============================================================
# 1. LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# 2. CREATE HUGGING FACE EMBEDDING MODEL
# ============================================================

embeddings = HuggingFaceEndpointEmbeddings(model="Octen/Octen-Embedding-0.6B")


# ============================================================
# 3. READ DOCUMENT
# ============================================================

pdf_path = (Path(__file__).parent/ "test_documents"/ "02_legal_contract.txt")

t = pdf_path.read_text()


# ============================================================
# 4. CHUNK DOCUMENT WITH METADATA
# ============================================================

def chunk_document_with_metadata(text,extraction_metadata,access_metadata):
    document_id = hashlib.sha256(text.encode()).hexdigest()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=100,
        chunk_overlap=20,
        separators=["\n\n","\n"," ",""]
    )

    chunks = text_splitter.split_text(text)

    documents = []

    for idx, chunk in enumerate(chunks):

        chunk_metadata = {
            **extraction_metadata,
            **access_metadata,
            "document_id": document_id,
            "chunk_id": f"{document_id}_{idx}",
            "chunk_index": idx,
            "chunk_size": len(chunk),
            "chunk_timestamp": datetime.datetime.now().isoformat(),
        }

        doc = Document(
            page_content=chunk,
            metadata=chunk_metadata
        )

        documents.append(doc)

    return documents


# ============================================================
# 5. EXTRACTION METADATA
# ============================================================

extraction_metadata = {
    "source": "02_legal_contract.txt",
    "pages": 1,
    "quality": 0.8,
    "extraction_method": "azure document intelligence",
}


# ============================================================
# 6. ACCESS METADATA
# ============================================================

access_metadata = {
    "access_level": "public",
    "department": "Legal"
}


# ============================================================
# 7. CREATE DOCUMENTS
# ============================================================

documents = chunk_document_with_metadata(t,extraction_metadata,access_metadata)

# ============================================================
# 8. DISPLAY DOCUMENTS
# ============================================================

for doc in documents:
    print(doc.metadata)
    print(doc.page_content)
    print("-" * 100)


# ============================================================
# 9. GENERATE EMBEDDINGS FOR DOCUMENT CHUNKS
# ============================================================

embedding_docs = embeddings.embed_documents([doc.page_content for doc in documents])

# ============================================================
# 10. DISPLAY DOCUMENT EMBEDDINGS
# ============================================================

for emb, doc in zip(embedding_docs,documents):
    print("*" * 100)
    print(f"Length of embedding: {len(emb)}")
    print(f"Embedding: {emb}")
    print("*" * 100)
    print(doc.page_content)
    print("-" * 100)
    print()

# ============================================================
# 11. CREATE QUERY
# ============================================================

query = "Liability and Damages"

# ============================================================
# 12. GENERATE QUERY EMBEDDING
# ============================================================

query_embedding = embeddings.embed_query(query)

# ============================================================
# 13. DISPLAY QUERY EMBEDDING
# ============================================================

print("*" * 100)
print(f"Length of query embedding: " f"{len(query_embedding)}")
print(f"Query embedding: {query_embedding}")
print("*" * 100)
print()

# ============================================================
# 14. COSINE SIMILARITY FUNCTION
# ============================================================

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# ============================================================
# 15. CALCULATE SIMILARITY
# ============================================================

similarities = [cosine_similarity(query_embedding,emb) for emb in embedding_docs]

# ============================================================
# 16. SORT BY SIMILARITY
# ============================================================

sorted_indices = np.argsort(similarities)[::-1]

# ============================================================
# 17. DISPLAY SEARCH RESULTS
# ============================================================

for idx in sorted_indices:
    print("*" * 100)
    print(f"Similarity: {similarities[idx]}")
    print(f"Document: "f"{documents[idx].page_content}")
    print("*" * 100)
    print()
    print("-" * 100)
    print()