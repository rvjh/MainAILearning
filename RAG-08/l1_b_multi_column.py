from pathlib import Path
import PyPDF2
import pdfplumber
import re

pdf_path = Path(__file__).parent / "test_documents" / "1810.04805v2.pdf"

def extract_pypdf2(pdf_path: Path) -> str:
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
print("pyPDF2 extracted text:")
print(extract_pypdf2(pdf_path)[:5000])
print("-" * 100)

def extract_pdfplumber(pdf_path: Path) -> str:
    # with open(pdf_path, "rb") as f:
    #     pdf = pdfplumber.open(f)
    #     text = ""
    #     for page in pdf.pages:
    #         text += page.extract_text()
    #     return text
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text(use_text_flow=True)
        return text
        
print("pdfplumber extracted text:")
print(extract_pdfplumber(pdf_path)[:5000])
print("-" * 100)