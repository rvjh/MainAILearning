"""
Access Control Demo - RAG with Department-Based Filtering

This script demonstrates:
1. Loading documents separately with different metadata per department
2. Database indexing for vector search and department filtering
3. Semantic search with department-level access control filtering

Prerequisites:
- PostgreSQL with pgvector: docker run --name pgvector-container \
  -e POSTGRES_USER=langchain \
  -e POSTGRES_PASSWORD=langchain \
  -e POSTGRES_DB=langchain \
  -p 6024:5432 \
  -d pgvector/pgvector:pg16

- Run schema from l3_prod_setup_notes.md (CREATE TABLE documents, etc.)
"""


from pathlib import Path
import hashlib
import sys

from dotenv import load_dotenv

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Json


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

CONNECTION_STRING = "postgresql://langchain:langchain@localhost:6024/langchain"

EMBEDDINGS_MODEL = HuggingFaceEndpointEmbeddings(
    model="Octen/Octen-Embedding-0.6B"
)


# Get the directory where this Python script is located.
BASE_DIR = Path(__file__).resolve().parent

DOCUMENT_DIR = BASE_DIR / "test_documents"


# ============================================================
# DOCUMENT CONFIGURATION
# ============================================================

# Format:
# (
#     file_path,
#     loader_type,
#     department,
#     access_level,
#     doc_type,
#     extraction_method,
# )

DOCUMENT_CONFIGS = [
    # --------------------------------------------------------
    # Engineering documents
    # --------------------------------------------------------

    (
        DOCUMENT_DIR / "03_aws_ec2_pricing.txt",
        "text",
        "engineering",
        "internal",
        "text",
        "textloader",
    ),

    (
        DOCUMENT_DIR / "04_cloud_computing_guide.txt",
        "text",
        "engineering",
        "internal",
        "text",
        "textloader",
    ),

    (
        DOCUMENT_DIR / "06_engineering_budget.txt",
        "text",
        "engineering",
        "internal",
        "text",
        "textloader",
    ),

    # --------------------------------------------------------
    # Finance documents
    # --------------------------------------------------------

    (
        DOCUMENT_DIR / "01_financial_report.txt",
        "text",
        "finance",
        "internal",
        "text",
        "textloader",
    ),

    (
        DOCUMENT_DIR / "financial_report.pdf",
        "pdf",
        "finance",
        "internal",
        "pdf",
        "pypdfloader",
    ),

    # --------------------------------------------------------
    # HR documents
    # --------------------------------------------------------

    (
        DOCUMENT_DIR / "05_hr_salary_data.txt",
        "text",
        "hr",
        "confidential",
        "text",
        "textloader",
    ),
]


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def sha256_hash(text: str) -> str:
    """
    Generate SHA-256 hash for document chunk content.
    """
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# ============================================================
# DOCUMENT LOADING
# ============================================================

def load_text_file(file_path: Path):
    """
    Load a text file using UTF-8 first.

    If UTF-8 fails, try common Windows encodings.
    This makes the loader more robust for .txt files created
    using Windows applications.
    """

    encodings_to_try = [
        "utf-8",
        "utf-8-sig",
        "cp1252",
        "latin-1",
    ]

    last_error = None

    for encoding in encodings_to_try:
        try:
            print(
                f"  Trying encoding '{encoding}' for "
                f"{file_path.name}"
            )

            loader = TextLoader(
                str(file_path),
                encoding=encoding,
            )

            docs = loader.load()

            print(
                f"  Successfully loaded using "
                f"'{encoding}'"
            )

            return docs

        except (UnicodeDecodeError, RuntimeError) as e:
            last_error = e

            print(
                f"  Failed with encoding "
                f"'{encoding}': {e}"
            )

    raise RuntimeError(
        f"Could not load text file: {file_path}\n"
        f"Last error: {last_error}"
    )


def load_documents(config: tuple):
    """
    Load documents from a single file with the given
    configuration.
    """

    (
        file_path,
        loader_type,
        department,
        access_level,
        doc_type,
        extraction_method,
    ) = config

    file_path = Path(file_path)

    print()
    print("-" * 60)
    print(f"Loading: {file_path}")
    print(f"Department: {department}")
    print(f"Access level: {access_level}")

    # --------------------------------------------------------
    # Check file exists
    # --------------------------------------------------------

    if not file_path.exists():
        raise FileNotFoundError(
            f"File does not exist: {file_path}\n"
            f"Absolute path: {file_path.resolve()}"
        )

    if not file_path.is_file():
        raise RuntimeError(
            f"Path is not a file: {file_path}"
        )

    # --------------------------------------------------------
    # Load PDF
    # --------------------------------------------------------

    if loader_type == "pdf":

        loader = PyPDFLoader(
            str(file_path)
        )

        docs = loader.load()

    # --------------------------------------------------------
    # Load text
    # --------------------------------------------------------

    elif loader_type == "text":

        docs = load_text_file(file_path)

    else:

        raise ValueError(
            f"Unsupported loader type: {loader_type}"
        )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {
        "department": department,
        "access_level": access_level,
        "doc_type": doc_type,
        "extraction_method": extraction_method,
        "source_file": str(file_path),
    }

    return docs, metadata


# ============================================================
# DATABASE SCHEMA
# ============================================================

def ensure_doc_type_constraint(conn) -> None:
    """
    Ensure doc_type constraint allows 'text'.
    """

    with conn.cursor() as cur:

        cur.execute(
            """
            ALTER TABLE documents
            DROP CONSTRAINT IF EXISTS documents_doc_type_check;
            """
        )

        cur.execute(
            """
            ALTER TABLE documents
            ADD CONSTRAINT documents_doc_type_check
            CHECK (
                doc_type IN (
                    'pdf',
                    'docx',
                    'html',
                    'code',
                    'email',
                    'text'
                )
            );
            """
        )

    conn.commit()

    print(
        "doc_type constraint updated "
        "to include 'text'."
    )


def ensure_indexes(conn) -> None:
    """
    Create indexes required for filtering and vector search.
    """

    with conn.cursor() as cur:

        # ----------------------------------------------------
        # JSONB metadata index
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_metadata_gin
            ON documents
            USING gin (metadata);
            """
        )

        # ----------------------------------------------------
        # Department index
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_department_idx
            ON documents (department);
            """
        )

        # ----------------------------------------------------
        # Access level index
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_access_level_idx
            ON documents (access_level);
            """
        )

        # ----------------------------------------------------
        # HNSW vector index
        # ----------------------------------------------------

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_hnsw_idx
            ON documents
            USING hnsw (embedding vector_cosine_ops);
            """
        )

    conn.commit()

    print(
        "Indexes created/verified successfully."
    )


# ============================================================
# STORE DOCUMENTS
# ============================================================

def load_and_store_department_documents(
    clear_existing: bool = False,
) -> None:
    """
    Load all configured documents, split them into chunks,
    generate embeddings, and store them in PostgreSQL.
    """

    # --------------------------------------------------------
    # Text splitter
    # --------------------------------------------------------

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=100,
        chunk_overlap=20,
    )

    print()
    print("=" * 60)
    print("CONNECTING TO POSTGRESQL")
    print("=" * 60)

    with psycopg.connect(
        CONNECTION_STRING
    ) as conn:

        register_vector(conn)

        print("PostgreSQL connection successful.")

        # ----------------------------------------------------
        # Ensure schema
        # ----------------------------------------------------

        ensure_doc_type_constraint(conn)

        # ----------------------------------------------------
        # Clear existing data if requested
        # ----------------------------------------------------

        if clear_existing:

            print()
            print("Clearing existing documents...")

            with conn.cursor() as cur:

                cur.execute(
                    "DELETE FROM documents;"
                )

            conn.commit()

            print(
                "Existing documents cleared."
            )

        # ----------------------------------------------------
        # Process each document
        # ----------------------------------------------------

        for config in DOCUMENT_CONFIGS:

            file_path = config[0]

            try:

                docs, meta_defaults = load_documents(
                    config
                )

            except FileNotFoundError as e:

                print()
                print(
                    f"WARNING: Skipping missing file:\n"
                    f"{e}"
                )

                continue

            except Exception as e:

                print()
                print(
                    f"ERROR loading {file_path}"
                )

                print(
                    f"Error type: "
                    f"{type(e).__name__}"
                )

                print(
                    f"Error details: {e}"
                )

                # Continue with remaining documents
                continue

            # ------------------------------------------------
            # Add metadata to each loaded document
            # ------------------------------------------------

            for doc in docs:

                doc.metadata = {
                    **doc.metadata,
                    **meta_defaults,
                }

            # ------------------------------------------------
            # Split documents into chunks
            # ------------------------------------------------

            split_docs = splitter.split_documents(
                docs
            )

            if not split_docs:

                print(
                    f"No chunks generated for "
                    f"{file_path}"
                )

                continue

            texts = [
                doc.page_content
                for doc in split_docs
                if doc.page_content.strip()
            ]

            if not texts:

                print(
                    f"No text content found in "
                    f"{file_path}"
                )

                continue

            print(
                f"Generated {len(texts)} chunks."
            )

            # ------------------------------------------------
            # Generate embeddings
            # ------------------------------------------------

            print(
                f"Generating embeddings for "
                f"{len(texts)} chunks..."
            )

            embeddings = (
                EMBEDDINGS_MODEL.embed_documents(
                    texts
                )
            )

            print(
                f"Generated {len(embeddings)} embeddings."
            )

            # ------------------------------------------------
            # Store chunks
            # ------------------------------------------------

            with conn.cursor() as cur:

                total_chunks = len(texts)

                for i, (doc, emb) in enumerate(
                    zip(split_docs, embeddings)
                ):

                    content = doc.page_content

                    if not content.strip():
                        continue

                    meta = doc.metadata or {}

                    # ----------------------------------------
                    # Get source file
                    # ----------------------------------------

                    source_file = meta.get(
                        "source_file"
                    )

                    if not source_file:

                        source_file = meta.get(
                            "source"
                        )

                    # ----------------------------------------
                    # Get page number
                    # ----------------------------------------

                    page_number = meta.get(
                        "page"
                    )

                    # ----------------------------------------
                    # Insert row
                    # ----------------------------------------

                    cur.execute(
                        """
                        INSERT INTO documents (
                            content,
                            embedding,
                            source_file,
                            page_number,
                            chunk_index,
                            total_chunks,
                            doc_hash,
                            department,
                            access_level,
                            created_by,
                            doc_type,
                            chunk_type,
                            extraction_method,
                            extraction_confidence,
                            chunk_length,
                            metadata
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        );
                        """,
                        (
                            content,
                            emb,
                            source_file,
                            page_number,
                            i,
                            total_chunks,
                            sha256_hash(content),
                            meta_defaults[
                                "department"
                            ],
                            meta_defaults[
                                "access_level"
                            ],
                            "system",
                            meta_defaults[
                                "doc_type"
                            ],
                            "text",
                            meta_defaults[
                                "extraction_method"
                            ],
                            0.95,
                            len(content),
                            Json(meta),
                        ),
                    )

            conn.commit()

            print()
            print(
                f"SUCCESS: Stored "
                f"{len(texts)} chunks"
            )

            print(
                f"File: {file_path.name}"
            )

            print(
                f"Department: "
                f"{meta_defaults['department']}"
            )

        # ----------------------------------------------------
        # Ensure indexes after loading
        # ----------------------------------------------------

        print()
        print("Creating/verifying indexes...")

        ensure_indexes(conn)

    print()
    print("=" * 60)
    print("DOCUMENT LOADING COMPLETE")
    print("=" * 60)


# ============================================================
# DEPARTMENT FILTERED SEARCH
# ============================================================

def query_by_department(
    query: str,
    department: str,
    k: int = 5,
) -> list:
    """
    Perform semantic search filtered by department.

    This provides department-level access control because
    results are restricted using:

        WHERE department = %s
    """

    print()
    print(
        f"Searching department: {department}"
    )

    # --------------------------------------------------------
    # Generate query embedding
    # --------------------------------------------------------

    query_embedding = (
        EMBEDDINGS_MODEL.embed_query(query)
    )

    # --------------------------------------------------------
    # Query PostgreSQL
    # --------------------------------------------------------

    with psycopg.connect(
        CONNECTION_STRING
    ) as conn:

        register_vector(conn)

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    id,
                    content,
                    department,
                    access_level,
                    source_file,
                    1 - (
                        embedding <=> %s::vector
                    ) AS similarity
                FROM documents
                WHERE department = %s
                ORDER BY
                    embedding <=> %s::vector
                LIMIT %s;
                """,
                (
                    query_embedding,
                    department,
                    query_embedding,
                    k,
                ),
            )

            rows = cur.fetchall()

    return rows


# ============================================================
# SEARCH ALL DEPARTMENTS
# ============================================================

def query_all_departments(
    query: str,
    k: int = 3,
) -> dict:
    """
    Run the same semantic query against each department.
    """

    departments = [
        "engineering",
        "finance",
        "hr",
    ]

    results = {}

    for department in departments:

        rows = query_by_department(
            query,
            department,
            k=k,
        )

        results[department] = rows

    return results


# ============================================================
# PRINT RESULTS
# ============================================================

def print_query_results(
    query: str,
    results: dict,
) -> None:
    """
    Pretty-print search results.
    """

    print()
    print("=" * 60)
    print(
        f'Query: "{query}"'
    )
    print("=" * 60)

    for department, rows in results.items():

        print()
        print(
            f"--- Department: "
            f"{department.upper()} ---"
        )

        if not rows:

            print("  (No results)")

            continue

        for row in rows:

            (
                doc_id,
                content,
                dept,
                access,
                source,
                similarity,
            ) = row

            preview = (
                content[:120]
                .replace("\n", " ")
            )

            if len(content) > 120:

                preview += "..."

            print(
                f"  [id={doc_id}] "
                f"[sim={similarity:.3f}] "
                f"{preview}"
            )

            print(
                f"    department: {dept}"
            )

            print(
                f"    access: {access}"
            )

            print(
                f"    source: {source}"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("DEPARTMENT ACCESS CONTROL RAG DEMO")
    print("=" * 60)

    print()
    print(
        f"Python script directory:"
    )

    print(
        f"  {BASE_DIR}"
    )

    print()
    print(
        f"Document directory:"
    )

    print(
        f"  {DOCUMENT_DIR}"
    )

    # --------------------------------------------------------
    # Check document directory
    # --------------------------------------------------------

    if not DOCUMENT_DIR.exists():

        print()
        print(
            "ERROR: test_documents directory "
            "does not exist."
        )

        print(
            f"Expected location:\n"
            f"{DOCUMENT_DIR}"
        )

        return

    # --------------------------------------------------------
    # Print configured files
    # --------------------------------------------------------

    print()
    print(
        "Checking configured documents..."
    )

    for config in DOCUMENT_CONFIGS:

        file_path = Path(config[0])

        status = (
            "FOUND"
            if file_path.exists()
            else "MISSING"
        )

        print(
            f"  [{status}] "
            f"{file_path.name}"
        )

    # --------------------------------------------------------
    # Determine whether to clear database
    # --------------------------------------------------------

    clear = (
        "--clear" in sys.argv
        or "-c" in sys.argv
    )

    if clear:

        print()
        print(
            "Database will be cleared "
            "before loading."
        )

    # --------------------------------------------------------
    # Load documents
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "LOADING DOCUMENTS"
    )
    print("=" * 60)

    load_and_store_department_documents(
        clear_existing=clear
    )

    # --------------------------------------------------------
    # Demo 1: Engineering
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "DEPARTMENT-FILTERED SEMANTIC SEARCH"
    )
    print("=" * 60)

    demo_queries = [
        (
            "What is AWS EC2 pricing?",
            "engineering",
        ),
        (
            "What is Q4 revenue?",
            "finance",
        ),
        (
            "What are salary ranges for engineers?",
            "hr",
        ),
    ]

    for query, expected_department in demo_queries:

        print()
        print(
            f'>>> Query: "{query}"'
        )

        print(
            f"    Expected department: "
            f"{expected_department}"
        )

        rows = query_by_department(
            query,
            expected_department,
            k=3,
        )

        if not rows:

            print(
                "    No results found."
            )

            continue

        for row in rows:

            (
                doc_id,
                content,
                department,
                access,
                source,
                similarity,
            ) = row

            preview = (
                content[:100]
                .replace("\n", " ")
            )

            if len(content) > 100:

                preview += "..."

            print()
            print(
                f"  [{department}] "
                f"similarity={similarity:.3f}"
            )

            print(
                f"  {preview}"
            )

            print(
                f"  source={source}"
            )

            print(
                f"  access={access}"
            )

    # --------------------------------------------------------
    # Demo 2: Cross-department comparison
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        'CROSS-DEPARTMENT COMPARISON: "cloud cost"'
    )
    print("=" * 60)

    all_results = query_all_departments(
        "cloud cost",
        k=2,
    )

    print_query_results(
        "cloud cost",
        all_results,
    )

    # --------------------------------------------------------
    # Finished
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "DEMO COMPLETE"
    )
    print("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
