"""Render sample PDFs: native digital (text layer) and scanned (image-only, forces OCR)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.config import SAMPLES_DIR
from src.samples import SAMPLES, SampleDoc


def _arial(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = Path(r"C:\Windows\Fonts") / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _write_ground_truth(sample: SampleDoc, pdf_path: Path) -> None:
    payload = {
        "key": sample.key,
        "kind": sample.kind,
        "title": sample.title,
        "kv": sample.kv,
        "tables": [
            {
                "name": table.name,
                "caption": table.caption,
                "headers": table.headers,
                "rows": table.rows,
            }
            for table in sample.tables
        ],
    }
    pdf_path.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _render_digital(sample: SampleDoc, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(dest),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    story: list = [
        Paragraph(sample.title, styles["Title"]),
        Paragraph(sample.subtitle, styles["Heading2"]),
        Spacer(1, 12),
    ]
    if sample.kv:
        kv_data = [["Field", "Value"], *[[k, v] for k, v in sample.kv.items()]]
        kv_table = Table(kv_data, colWidths=[2.2 * inch, 4.6 * inch])
        kv_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b4d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#7a8a96")),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f4f7f9")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story += [kv_table, Spacer(1, 16)]
    for para in sample.paragraphs:
        story += [Paragraph(para, styles["BodyText"]), Spacer(1, 10)]
    for spec in sample.tables:
        story.append(Paragraph(spec.caption, styles["Heading3"]))
        data = [spec.headers, *spec.rows]
        col_w = 6.8 * inch / max(len(spec.headers), 1)
        table = Table(data, colWidths=[col_w] * len(spec.headers))
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b4d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#5c6b75")),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f6")]),
        ]
        table.setStyle(TableStyle(style_cmds))
        story += [table, Spacer(1, 14)]
    doc.build(story)


def _render_scanned(sample: SampleDoc, dest: Path) -> None:
    """Image-only PDF: no text layer, so Docling must OCR."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1700, 2200
    img = Image.new("RGB", (width, height), (248, 246, 240))
    draw = ImageDraw.Draw(img)
    title_font = _arial(36, bold=True)
    sub_font = _arial(20)
    body_font = _arial(18)
    header_font = _arial(16, bold=True)
    cell_font = _arial(16)

    y = 80
    draw.text((80, y), sample.title, fill=(20, 32, 42), font=title_font)
    y += 55
    draw.text((80, y), sample.subtitle, fill=(60, 72, 82), font=sub_font)
    y += 50
    draw.line((80, y, width - 80, y), fill=(31, 59, 77), width=3)
    y += 30

    if sample.kv:
        for key, value in sample.kv.items():
            draw.text((80, y), f"{key}: {value}", fill=(20, 32, 42), font=body_font)
            y += 32
        y += 16

    for para in sample.paragraphs:
        draw.text((80, y), para[:95], fill=(40, 48, 56), font=body_font)
        y += 40

    for spec in sample.tables:
        draw.text((80, y), spec.caption, fill=(20, 32, 42), font=header_font)
        y += 36
        cols = len(spec.headers)
        table_w = width - 160
        col_w = table_w / cols
        row_h = 42
        grid = [spec.headers, *spec.rows]
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                x0 = 80 + c * col_w
                y0 = y + r * row_h
                x1 = x0 + col_w
                y1 = y0 + row_h
                fill = (31, 59, 77) if r == 0 else ((255, 255, 255) if r % 2 else (238, 243, 246))
                text_fill = (255, 255, 255) if r == 0 else (20, 32, 42)
                draw.rectangle((x0, y0, x1, y1), fill=fill, outline=(90, 105, 115), width=1)
                draw.text((x0 + 8, y0 + 10), str(cell), fill=text_fill, font=header_font if r == 0 else cell_font)
        y += row_h * len(grid) + 40

    # Mild scan noise so this is not a perfectly clean raster.
    pixels = img.load()
    for n in range(0, width * height, 97):
        x, yy = n % width, (n // width) % height
        r, g, b = pixels[x, yy]
        pixels[x, yy] = (max(0, r - 6), max(0, g - 5), max(0, b - 4))

    png_path = dest.with_suffix(".png")
    img.save(png_path, "PNG")
    img.save(dest, "PDF", resolution=200.0)


def generate_all(out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or SAMPLES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for sample in SAMPLES:
        dest = out_dir / f"{sample.key}.pdf"
        if sample.kind == "scanned":
            _render_scanned(sample, dest)
        else:
            _render_digital(sample, dest)
        _write_ground_truth(sample, dest)
        written.append(dest)
        print(f"wrote {dest}")
    return written


if __name__ == "__main__":
    generate_all()
