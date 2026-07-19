from .pdf import extract_pdf
from .repo import extract_repo

def extract_text(s: str, *, label: str = "note") -> tuple[str, dict]:
    return s, {"source": label}