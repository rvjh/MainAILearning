from langchain_text_splitters import RecursiveCharacterTextSplitter
from pathlib import Path

pdf_path = Path(__file__).parent / "test_documents" / "02_legal_contract.txt"

text = pdf_path.read_text()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=100,
                    chunk_overlap=20,
                    separators=["\n\n", "\n", " ", ""])

chunks = text_splitter.split_text(text)

for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}: {len(chunk)}")
    print(chunk)
    print("-" * 100)