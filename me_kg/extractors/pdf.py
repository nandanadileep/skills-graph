from __future__ import annotations
import fitz  # pymupdf

def extract_pdf(path: str, *, ocr: bool = True) -> tuple[str, dict]:
    doc = fitz.open(path)
    pages: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        if (not text.strip()) and ocr:
            text = _ocr_page(page)
        pages.append(text)
    full = "\n\n".join(p for p in pages if p.strip())
    meta = {
        "page_count": len(doc),
        "title": doc.metadata.get("title") or "",
        "author": doc.metadata.get("author") or "",
        "subject": doc.metadata.get("subject") or "",
    }
    doc.close()
    return full, meta

def _ocr_page(page) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img)
    except Exception:
        return ""