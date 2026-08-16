# Test Documents for Class Demos

This folder contains test documents used by the class demo scripts. Each document is in its **native format** so demos can show format-appropriate loading and processing.

## Formats and Creation

| Format | Files | Created by | Used by |
|--------|--------|------------|---------|
| **PDF** | `financial_report.pdf`, `multi_column_report.pdf` | `generate_demo_pdf.py` | Demo 2 (document extraction) |
| **TXT** | `01_*.txt` … `09_*.txt` | In repo or add manually | Demos 1–7, load_documents |
| **PY** | `10_code_example.py` | In repo or add manually | Demo 3 (code/AST chunking) |
| **DOCX** | `11_company_policy.docx` | In repo or create with python-docx | load_documents, multi-format demo |
| **HTML** | `12_blog_post.html` | In repo or add manually | load_documents, multi-format demo |

**Optional: generate PDFs (from repo root):**
```bash
python class_demo/test_documents/generate_demo_pdf.py   # PDFs for Demo 2
```
Demos read from these files when present; each demo script includes inline fallback content if a file is missing.

- **financial_report.pdf** / **multi_column_report.pdf**: Native PDF for extraction demo. PyPDF2 vs pdfplumber comparison; table and multi-column layout.
- **01–09**: Plain text (`.txt`) for RAG context, chunking, embeddings, hybrid search, access control.
- **10_code_example.py**: Native Python for code/AST chunking.
- **11_company_policy.docx**, **12_blog_post.html**: Native Word and HTML for multi-format loading in `load_documents.py` (format-aware readers).

---

## Document Overview

### 01_financial_report.txt
**Purpose**: Document extraction and chunking demo
- Contains structured financial data (tables, metrics)
- Tests extraction quality (tables, formatting)
- Used in: Demo 2 (Document Extraction), Demo 3 (Chunking)

**Key Content**:
- Q4 revenue: $4.2M
- Quarterly revenue table
- Key metrics (acquisition, growth, retention)

---

### 02_legal_contract.txt
**Purpose**: Chunking demo (semantic boundaries)
- Contains legal clauses with specific sections
- Tests sentence-aware chunking
- Used in: Demo 3 (Chunking)

**Key Content**:
- Section 7.3: Liability and damages ($500,000 cap)
- Section 2.4: Definitions
- Tests chunking across section boundaries

---

### 03_aws_ec2_pricing.txt
**Purpose**: Hybrid search demo
- Contains exact terms (AWS, EC2, November 2024)
- Tests keyword vs semantic search
- Used in: Demo 7 (Hybrid Search)

**Key Content**:
- Exact product names: "AWS EC2"
- Specific dates: "November 2024"
- Pricing information

---

### 04_cloud_computing_guide.txt
**Purpose**: Hybrid search demo (semantic match)
- Contains semantically similar content to #3
- No exact term matches ("cloud computing" vs "AWS EC2")
- Used in: Demo 7 (Hybrid Search)

**Key Content**:
- Cloud computing strategies
- Cost optimization (semantically related to pricing)
- No exact term matches with #3

---

### 05_hr_salary_data.txt
**Purpose**: Access control demo
- CONFIDENTIAL access level
- HR department only
- Tests data leakage prevention
- Used in: Demo 6 (Access Control)

**Key Content**:
- Salary ranges by department
- Q4 salary adjustments
- Sensitive compensation data

---

### 06_engineering_budget.txt
**Purpose**: Access control demo
- INTERNAL access level
- Engineering department
- Tests department-based filtering
- Used in: Demo 6 (Access Control)

**Key Content**:
- Q4 budget allocation
- Engineering-specific costs
- Should NOT be visible to finance users

---

### 07_public_company_info.txt
**Purpose**: Access control demo
- PUBLIC access level
- General company information
- Tests public access filtering
- Used in: Demo 6 (Access Control)

**Key Content**:
- Company overview
- Public contact information
- Accessible to all users

---

### 08_semantic_similarity_test.txt
**Purpose**: Embeddings demo
- Contains sentences for similarity testing
- Tests semantic vs keyword matching
- Used in: Demo 4 (Embeddings)

**Key Content**:
- "The cat sat on the mat" (similar to "feline rested on rug")
- "I love eating pizza" (different topic)
- "The dog barked" (different topic)

---

### 09_multi_column_document.txt
**Purpose**: Document extraction demo
- Simulates multi-column layout (academic paper)
- Tests layout-aware extraction
- Used in: Demo 2 (Document Extraction)

**Key Content**:
- Research paper format
- Abstract, Introduction, Methodology sections
- Tests extraction of structured academic content

---

### 10_code_example.py
**Purpose**: Chunking demo (code-specific)
- **Format**: Python (`.py`) — native code format
- Python code with functions and classes
- Tests code-aware chunking (AST)
- Used in: Demo 3 (Chunking)

**Key Content**:
- `calculate_revenue()` function
- `FinancialReport` class
- Tests chunking by function/class boundaries

---

### 11_company_policy.docx
**Purpose**: Multi-format document processing
- **Format**: Word (`.docx`) — native DOCX
- Created by `ensure_demo_documents()` when python-docx is installed
- Used by: `load_documents.py` (format-aware loader)

---

### 12_blog_post.html
**Purpose**: Multi-format document processing
- **Format**: HTML (`.html`) — native web
- Created by `ensure_demo_documents()`
- Used by: `load_documents.py` (BeautifulSoup or strip tags)

---

## Metadata

All documents have associated metadata in `document_metadata.json`:

- **source_file**: File name
- **department**: finance, engineering, hr, legal, marketing, research, test
- **access_level**: public, internal, confidential
- **doc_type**: report, contract, technical, guide, salary, budget, etc.
- **tenant_id**: company-abc (for multi-tenancy testing)
- **created_by**: Email of creator
- **tags**: Array of relevant tags

## Usage in Demos

### Demo 1 (RAG Fundamentals)
- Uses: 01_financial_report.txt (for RAG context)

### Demo 2 (Document Extraction)
- Uses: 01_financial_report.txt, 09_multi_column_document.txt
- Tests: Extraction quality, table preservation, layout handling

### Demo 3 (Chunking)
- Uses: 02_legal_contract.txt, 10_code_example.py
- Tests: Sentence-aware chunking, code chunking

### Demo 4 (Embeddings)
- Uses: 08_semantic_similarity_test.txt
- Tests: Semantic similarity, keyword vs semantic search

### Demo 5 (PGVector)
- Uses: All documents
- Tests: Vector storage, schema design

### Demo 6 (Access Control)
- Uses: 01_financial_report.txt, 05_hr_salary_data.txt, 06_engineering_budget.txt, 07_public_company_info.txt
- Tests: Department filtering, access level filtering, data leakage prevention

### Demo 7 (Hybrid Search)
- Uses: 03_aws_ec2_pricing.txt, 04_cloud_computing_guide.txt
- Tests: Vector search (semantic) vs keyword search (exact terms)

## Test Scenarios

### Access Control Scenarios

**User: Finance Analyst**
- Should see: 01_financial_report.txt
- Should NOT see: 05_hr_salary_data.txt, 06_engineering_budget.txt
- Can see: 07_public_company_info.txt

**User: Engineering Team**
- Should see: 03_aws_ec2_pricing.txt, 04_cloud_computing_guide.txt, 06_engineering_budget.txt
- Should NOT see: 05_hr_salary_data.txt, 01_financial_report.txt (confidential)
- Can see: 07_public_company_info.txt

**User: Public User**
- Should see: 07_public_company_info.txt
- Should NOT see: All other documents

### Hybrid Search Scenarios

**Query: "AWS EC2 pricing November 2024"**
- Vector search: Might rank 04_cloud_computing_guide.txt high (semantic similarity)
- Keyword search: Should rank 03_aws_ec2_pricing.txt #1 (exact terms)
- Hybrid search: Should combine both, with 03_aws_ec2_pricing.txt winning

**Query: "cloud cost optimization"**
- Vector search: Should rank 04_cloud_computing_guide.txt high
- Keyword search: Might miss if no exact term match
- Hybrid search: Should find relevant documents

## Loading Documents in Demos

```python
from langchain.schema import Document
import json

# Load document with metadata
def load_document_with_metadata(filename):
    with open(f'test_documents/{filename}', 'r') as f:
        content = f.read()
    
    with open('test_documents/document_metadata.json', 'r') as f:
        metadata = json.load(f)[filename]
    
    return Document(page_content=content, metadata=metadata)

# Example
doc = load_document_with_metadata('01_financial_report.txt')
```

## Notes

- **Native formats**: PDF for extraction demo; .txt for content; .py for code; .docx and .html for multi-format loading.
- `load_documents.py` uses format-appropriate loaders: plain text for .txt/.py, python-docx for .docx, BeautifulSoup for .html.
- Metadata is in `document_metadata.json`. Add 01–12 files to this folder as needed; demos use inline fallbacks when files are missing.
- PDFs: run `generate_demo_pdf.py` (requires reportlab).
