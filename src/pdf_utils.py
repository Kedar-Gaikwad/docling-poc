"""PDF helpers: page count and splitting for multi-page Textract / parallel Docling."""

from __future__ import annotations

from pathlib import Path


def page_count(pdf_path: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()


def split_pdf(pdf_path: Path, dest_dir: Path, *, pages_per_chunk: int = 1) -> list[Path]:
    """Write sequential chunks. pages_per_chunk=1 yields one file per page."""
    import pypdfium2 as pdfium

    pdf_path = Path(pdf_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = pdfium.PdfDocument(str(pdf_path))
    written: list[Path] = []
    try:
        n = len(src)
        start = 0
        chunk_i = 1
        while start < n:
            end = min(start + pages_per_chunk, n)
            dst = pdfium.PdfDocument.new()
            dst.import_pages(src, list(range(start, end)))
            out = dest_dir / f"{pdf_path.stem}.p{start + 1:03d}-{end:03d}.pdf"
            dst.save(str(out))
            dst.close()
            written.append(out)
            start = end
            chunk_i += 1
    finally:
        src.close()
    return written
