"""
Extract text from a scanned/image PDF using Tesseract OCR.

Tesseract works on images, not PDFs directly, so we:
  1. Convert each PDF page to an image (pdf2image)
  2. Run Tesseract OCR on each image (pytesseract)
  3. Combine the text from all pages

Requirements:
  - pip: pytesseract, pdf2image, Pillow
  - System: Tesseract binary installed
    - macOS:   brew install tesseract poppler
    - Ubuntu:  apt-get install tesseract-ocr poppler-utils
    - Windows: Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki

"""

from pathlib import Path

CLASS_DEMO_DIR = Path(__file__).resolve().parent
PDF_PATH = CLASS_DEMO_DIR / "image_scan.pdf"


def extract_text_with_tesseract(pdf_path: str | Path, lang: str = "eng", dpi: int = 200) -> tuple[str, int]:
    """
    Convert PDF pages to images and run Tesseract OCR on each.
    Returns (combined text from all pages, number of pages).
    """
    import pytesseract
    from pdf2image import convert_from_path

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Convert PDF to list of PIL Images (one per page)
    # Higher DPI = better accuracy for small text, but slower
    print(f"Converting PDF to images (DPI={dpi})...")
    images = convert_from_path(str(pdf_path), dpi=dpi)
    num_pages = len(images)

    all_text = []
    for i, img in enumerate(images):
        print(f"  OCR page {i + 1}/{num_pages}...")
        text = pytesseract.image_to_string(img, lang=lang)
        all_text.append(text)

    return "\n\n".join(all_text), num_pages


def main():
    print("=" * 60)
    print("Tesseract OCR: Extract text from image_scan.pdf")
    print("=" * 60)

    if not PDF_PATH.exists():
        print(f"Error: PDF not found at {PDF_PATH}")
        return

    try:
        text, num_pages = extract_text_with_tesseract(PDF_PATH)
    except Exception as e:
        print(f"OCR failed: {e}")
        if "pdf2image" in str(type(e).__module__):
            print("Tip: Install poppler. macOS: brew install poppler")
        if "tesseract" in str(e).lower() or "pytesseract" in str(type(e).__module__):
            print("Tip: Install Tesseract. macOS: brew install tesseract")
        return

    # Summary
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    print(f"\nExtracted {len(text)} characters, {len(lines)} non-empty lines from {num_pages} page(s).")

    # Show first 1500 chars
    preview = text.strip()[:1500]
    print("\n--- Preview (first ~1500 chars) ---")
    print(preview)
    if len(text) > 1500:
        print("\n... [truncated] ...")

    # Optionally save full text to a file
    out_txt = CLASS_DEMO_DIR / "image_scan_extracted.txt"
    out_txt.write_text(text, encoding="utf-8")
    print(f"\nFull text saved to: {out_txt}")


if __name__ == "__main__":
    main()
