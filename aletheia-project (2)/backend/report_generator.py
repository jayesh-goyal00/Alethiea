"""Generates evidence report PDFs using ReportLab.

Contains SHA-256 hashes, video metadata, analysis score,
technical checks, and cybercrime reporting details.
"""
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_evidence_pdf(output_path, data):
    """Builds an official evidence report PDF.
    
    data dict contains:
      - report_id: str
      - file_name: str
      - sha256_original: str
      - sha256_portal: str (or None)
      - duration: str
      - fps: str
      - score: int
      - verdict: str
      - checks: list of {label, text, ok}
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
    )
    section_title = ParagraphStyle(
        "SecTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    mono_style = ParagraphStyle(
        "DocMono",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )
    disclaimer_style = ParagraphStyle(
        "DocDisclaimer",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748b"),
    )

    story = []

    # Title & Header
    story.append(Paragraph("Aletheia — Video Forensic Evidence Report", title_style))
    story.append(Spacer(1, 4))
    date_str = datetime.now().strftime("%d %b %Y, %H:%M:%S UTC")
    story.append(Paragraph(f"Verification Certificate • Generated: {date_str} • Report ID: {data.get('report_id', 'N/A')}", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=14))

    # Video Metadata Table
    meta_data = [
        [Paragraph("<b>Original Video Name</b>", body_style), Paragraph(str(data.get("file_name", "N/A")), body_style)],
        [Paragraph("<b>Duration</b>", body_style), Paragraph(str(data.get("duration", "N/A")), body_style)],
        [Paragraph("<b>Frames Per Second (FPS)</b>", body_style), Paragraph(str(data.get("fps", "N/A")), body_style)],
    ]
    meta_table = Table(meta_data, colWidths=[150, 380])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    story.append(Paragraph("1. Video Information", section_title))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # Cryptographic Hash Signatures
    story.append(Paragraph("2. Cryptographic Fingerprints (SHA-256)", section_title))
    hash_rows = [
        [
            Paragraph("<b>Original Video SHA-256:</b>", body_style),
            Paragraph(f"<font color='#0f172a'>{data.get('sha256_original', 'N/A')}</font>", mono_style),
        ]
    ]
    if data.get("sha256_portal"):
        hash_rows.append([
            Paragraph("<b>Compressed Portal Copy SHA-256:</b>", body_style),
            Paragraph(f"<font color='#0f172a'>{data.get('sha256_portal')}</font>", mono_style),
        ])
    hash_table = Table(hash_rows, colWidths=[180, 350])
    hash_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
    ]))
    story.append(hash_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph("<i>Notice: Retain your original video file without altering it to maintain verification chain of custody.</i>", subtitle_style))
    story.append(Spacer(1, 12))

    # Forensic Analysis Verdict
    score = data.get("score", 50)
    verdict = data.get("verdict", "Not sure")
    band_color = colors.HexColor("#ef4444") if score >= 70 else (colors.HexColor("#eab308") if score >= 40 else colors.HexColor("#22c55e"))

    story.append(Paragraph("3. Technical Analysis Verdict", section_title))
    verdict_data = [
        [
            Paragraph(f"<b>Estimated Tampering Likelihood:</b> {score}%", body_style),
            Paragraph(f"<b>Classification:</b> <font color='{band_color.hexval()}'><b>{verdict.upper()}</b></font>", body_style),
        ]
    ]
    verdict_table = Table(verdict_data, colWidths=[265, 265])
    verdict_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 10))

    # Detailed Checks Table
    story.append(Paragraph("4. Signal Breakdown", section_title))
    checks = data.get("checks", [])
    check_rows = [[Paragraph("<b>Signal / Feature</b>", body_style), Paragraph("<b>Status</b>", body_style), Paragraph("<b>Finding</b>", body_style)]]
    for c in checks:
        ok = c.get("ok", False)
        status_text = "<font color='#16a34a'><b>PASSED</b></font>" if ok else "<font color='#dc2626'><b>SUSPICIOUS / UNCLEAR</b></font>"
        check_rows.append([
            Paragraph(f"<b>{c.get('label', '')}</b>", body_style),
            Paragraph(status_text, body_style),
            Paragraph(c.get("text", ""), body_style),
        ])

    checks_table = Table(check_rows, colWidths=[140, 130, 260])
    checks_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(checks_table)
    story.append(Spacer(1, 16))

    # Cybercrime reporting info & disclaimer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=10))
    story.append(Paragraph(
        "<b>Reporting Instructions:</b> If you believe this video was created or used maliciously, file a complaint on the National Cyber Crime Reporting Portal at <b>cybercrime.gov.in</b> (Report Suspect &gt; Deepfake) or call the Cyber Helpline at <b>1930</b>. Attach this PDF report alongside the video as supporting evidence.",
        body_style,
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Legal & Technical Disclaimer:</b> This report is generated by automated digital signal analysis. Remote photoplethysmography (rPPG) and biological rhythm analysis are supporting forensic techniques. Compression, poor lighting, or camera stabilization can alter optical skin reflectance. This report does not constitute a final judicial determination. Aletheia is an independent aid and is not operated by I4C or government agencies.",
        disclaimer_style,
    ))

    doc.build(story)
    return output_path

