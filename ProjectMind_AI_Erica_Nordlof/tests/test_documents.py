from __future__ import annotations

import io

from reportlab.pdfgen import canvas

from documents import extract_document, split_blocks


def make_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 760, "Kursen omfattar 60 YH-poäng")
    pdf.showPage()
    pdf.drawString(72, 760, "Examination sker genom individuell uppgift")
    pdf.save()
    return buffer.getvalue()


def test_pdf_extraction_has_page_sources():
    result = extract_document(make_pdf(), "kursplan.pdf", "application/pdf")
    assert result.locator_count == 2
    assert "sida 1" in result.text
    assert "60 YH-poäng" in result.text
    assert "sida 2" in result.text
    assert len(split_blocks(result.text)) == 2
