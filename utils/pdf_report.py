"""
utils/pdf_report.py
====================
Professional, branded PDF report engine for FinTwin AI.

This module is purely a PRESENTATION layer. It never recalculates or derives
financial data — every value, table and chart it renders is supplied by the
caller (already computed elsewhere in the app: Digital Twin engine, ML
models, forecasting engine, etc.). This keeps the report generator decoupled
from business logic, so existing calculations remain completely untouched.

Usage
-----
    from utils.pdf_report import FinTwinPDFReport

    report = FinTwinPDFReport(
        report_title="Digital Twin Profile Report",
        user_id=twin.user_id,
        report_id=f"DT-{twin.user_id}",
    )
    report.add_section("User Profile")
    report.add_key_value_grid({"Name": "...", "Age": "..."})
    report.add_dataframe_table(df, title="Income Breakdown")
    report.add_plotly_figure(fig, caption="Monthly Cash Flow")
    pdf_bytes = report.build()

    st.download_button("Download PDF Report", data=pdf_bytes,
                        file_name=report.suggested_filename("digital_twin"),
                        mime="application/pdf")
"""

from __future__ import annotations

import io
import os
import re
import html
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# --------------------------------------------------------------------------- #
# Optional vector logo support (SVG -> ReportLab drawing, no Cairo required)
# --------------------------------------------------------------------------- #
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF

    _SVG_AVAILABLE = True
except ImportError:  # pragma: no cover - svglib is an optional dependency
    _SVG_AVAILABLE = False

# --------------------------------------------------------------------------- #
# Brand palette (matches the FinTwin AI Streamlit theme in utils/ui_components.py)
# --------------------------------------------------------------------------- #
BRAND_PRIMARY = colors.HexColor("#4F8CFF")
BRAND_CYAN = colors.HexColor("#00D4FF")
BRAND_GREEN = colors.HexColor("#22C55E")
BRAND_DARK = colors.HexColor("#0F172A")
BRAND_GREY = colors.HexColor("#64748B")
BRAND_LIGHT_ROW = colors.HexColor("#F1F5F9")
BRAND_BORDER = colors.HexColor("#CBD5E1")

_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)
LOGO_PATH = os.path.join(_ASSETS_DIR, "logos", "8_transparent.svg")

COMPANY_NAME = "FinTwin AI"

DISCLAIMER_TEXT = (
    "Disclaimer: This report is generated using Artificial Intelligence and predictive "
    "models. AI-generated insights may contain inaccuracies or omissions. Please verify "
    "all important financial information before making any financial or investment "
    "decisions."
)

PAGE_SIZE = A4
PAGE_W, PAGE_H = PAGE_SIZE
MARGIN = 16 * mm
HEADER_RESERVE = 26 * mm
FOOTER_RESERVE = 14 * mm
CONTENT_WIDTH = PAGE_W - 2 * MARGIN


# --------------------------------------------------------------------------- #
# Header / Footer drawing helpers
# --------------------------------------------------------------------------- #
def _draw_logo(c: pdfcanvas.Canvas, x: float, y_baseline: float, target_h: float = 8.5 * mm):
    """Draw the FinTwin AI logo (vector SVG if available, else a text wordmark)."""
    if _SVG_AVAILABLE and os.path.exists(LOGO_PATH):
        try:
            drawing = svg2rlg(LOGO_PATH)
            scale = target_h / float(drawing.height)
            c.saveState()
            c.translate(x, y_baseline)
            c.scale(scale, scale)
            renderPDF.draw(drawing, c, 0, 0)
            c.restoreState()
            return drawing.width * scale
        except Exception:
            pass
    # Fallback: styled text wordmark
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(BRAND_PRIMARY)
    c.drawString(x, y_baseline + 1, "FinTwin")
    c.setFillColor(BRAND_DARK)
    c.drawString(x + c.stringWidth("FinTwin", "Helvetica-Bold", 13), y_baseline + 1, " AI")
    return 45


def _draw_header(c: pdfcanvas.Canvas, ctx: Dict[str, Any]):
    c.saveState()
    top = PAGE_H - MARGIN
    _draw_logo(c, MARGIN, top - 9 * mm)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(BRAND_DARK)
    c.drawRightString(PAGE_W - MARGIN, top - 3 * mm, ctx["report_title"])

    c.setFont("Helvetica", 7.7)
    c.setFillColor(BRAND_GREY)
    meta_bits = [f"Generated: {ctx['generated_at']}"]
    if ctx.get("report_id"):
        meta_bits.append(f"Report ID: {ctx['report_id']}")
    c.drawRightString(PAGE_W - MARGIN, top - 7.6 * mm, "   |   ".join(meta_bits))

    c.setFont("Helvetica", 7.7)
    c.drawRightString(
        PAGE_W - MARGIN, top - 11.2 * mm, f"Page {ctx['page_num']} of {ctx['total_pages']}"
    )

    c.setStrokeColor(BRAND_PRIMARY)
    c.setLineWidth(1.1)
    c.line(MARGIN, top - 13 * mm, PAGE_W - MARGIN, top - 13 * mm)
    c.restoreState()


def _draw_footer(c: pdfcanvas.Canvas, ctx: Dict[str, Any]):
    c.saveState()
    y = MARGIN - 4 * mm
    c.setStrokeColor(BRAND_BORDER)
    c.setLineWidth(0.6)
    c.line(MARGIN, y + 5 * mm, PAGE_W - MARGIN, y + 5 * mm)

    c.setFont("Helvetica", 7.3)
    c.setFillColor(BRAND_GREY)
    c.drawString(MARGIN, y, f"{COMPANY_NAME}  •  Generated by AI  •  Confidential")
    c.drawRightString(PAGE_W - MARGIN, y, f"Page {ctx['page_num']} of {ctx['total_pages']}")
    c.restoreState()


class _NumberedCanvas(pdfcanvas.Canvas):
    """Buffers every page so the true 'Page X of Y' total can be rendered."""

    def __init__(self, *args, report_ctx: Dict[str, Any], **kwargs):
        super().__init__(*args, **kwargs)
        self._report_ctx = report_ctx
        self._saved_states: List[dict] = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            ctx = dict(self._report_ctx)
            ctx["page_num"] = self._pageNumber
            ctx["total_pages"] = total_pages
            _draw_header(self, ctx)
            _draw_footer(self, ctx)
            super().showPage()
        super().save()


# --------------------------------------------------------------------------- #
# Paragraph / table styles
# --------------------------------------------------------------------------- #
def _build_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "H1": ParagraphStyle(
            "FT_H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=15, textColor=BRAND_DARK, spaceBefore=10, spaceAfter=6,
            borderPadding=0,
        ),
        "H2": ParagraphStyle(
            "FT_H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11.5, textColor=BRAND_PRIMARY, spaceBefore=8, spaceAfter=4,
        ),
        "Body": ParagraphStyle(
            "FT_Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.3, leading=13, textColor=BRAND_DARK, spaceAfter=4,
        ),
        "Caption": ParagraphStyle(
            "FT_Caption", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=8, leading=11, textColor=BRAND_GREY, alignment=TA_CENTER,
            spaceBefore=2, spaceAfter=10,
        ),
        "CoverTitle": ParagraphStyle(
            "FT_CoverTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=24, textColor=BRAND_DARK, alignment=TA_LEFT, spaceAfter=6,
        ),
        "CoverSub": ParagraphStyle(
            "FT_CoverSub", parent=base["BodyText"], fontName="Helvetica",
            fontSize=11.5, textColor=BRAND_GREY, alignment=TA_LEFT, spaceAfter=4,
        ),
        "Disclaimer": ParagraphStyle(
            "FT_Disclaimer", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=7.8, leading=11, textColor=BRAND_GREY, spaceBefore=16,
            borderColor=BRAND_BORDER, borderWidth=0.6, borderPadding=8,
            backColor=BRAND_LIGHT_ROW,
        ),
        "TableCell": ParagraphStyle(
            "FT_TableCell", fontName="Helvetica", fontSize=8.3, leading=10.5,
            textColor=BRAND_DARK,
        ),
        "TableHeader": ParagraphStyle(
            "FT_TableHeader", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5,
            textColor=colors.white,
        ),
    }
    return styles


def _clean_text_for_pdf(text: str, is_html: bool = True) -> str:
    if text is None:
        return ""
    text = str(text)
    
    # Replace Font Awesome / HTML icon tags before escaping
    text = re.sub(r'<i[^>]*arrow-trend-up[^>]*>.*?</i>', '(+) ', text, flags=re.IGNORECASE)
    text = re.sub(r'<i[^>]*arrow-trend-down[^>]*>.*?</i>', '(-) ', text, flags=re.IGNORECASE)
    text = re.sub(r'<i[^>]*circle-check[^>]*>.*?</i>', '[OK] ', text, flags=re.IGNORECASE)
    text = re.sub(r'<i[^>]*triangle-exclamation[^>]*>.*?</i>', '[!] ', text, flags=re.IGNORECASE)
    text = re.sub(r'<i\s+class=[^>]*>.*?</i>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:span|div|p|small|section|aside|header|strong)[^>]*>', '', text, flags=re.IGNORECASE)
    
    # Convert markdown bold (**) and italic (*) to HTML tags
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # Convert unicode symbols & emojis to PDF-safe equivalents
    text = text.replace("₹", "Rs. ")
    text = text.replace("\U0001f7e2", "+ ")
    text = text.replace("\U0001f534", "- ")
    text = text.replace("\u26a0\ufe0f", "[!] ")
    text = text.replace("<strong>", "<b>").replace("</strong>", "</b>")
    
    if is_html:
        safe = html.escape(text)
        # Restore allowed ReportLab tag markups
        safe = safe.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
        safe = safe.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
        safe = safe.replace("&lt;u&gt;", "<u>").replace("&lt;/u&gt;", "</u>")
        safe = safe.replace("&lt;br/&gt;", "<br/>").replace("&lt;br&gt;", "<br/>")
        safe = safe.replace("\n", "<br/>")
        return safe
    else:
        return html.escape(text)


def _fmt_cell(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return _clean_text_for_pdf(val)


def _convert_to_light_mode(fig):
    import copy
    fig_light = copy.deepcopy(fig)
    
    # Apply white template
    try:
        fig_light.update_layout(template="plotly_white")
    except Exception:
        pass
    
    # Make background transparent to match PDF background
    fig_light.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    
    # Update global layout font to dark slate
    if fig_light.layout.font:
        if isinstance(fig_light.layout.font, dict):
            fig_light.layout.font["color"] = "#1E293B"
        else:
            fig_light.layout.font.color = "#1E293B"
    else:
        fig_light.layout.font = dict(color="#1E293B")
        
    # Update title font to dark slate
    if fig_light.layout.title:
        title = fig_light.layout.title
        if isinstance(title, dict):
            if "font" in title and title["font"]:
                if isinstance(title["font"], dict):
                    title["font"]["color"] = "#0F172A"
                else:
                    title["font"].color = "#0F172A"
            else:
                title["font"] = dict(color="#0F172A")
        else:
            if hasattr(title, "font") and title.font:
                title.font.color = "#0F172A"
            else:
                title.font = dict(color="#0F172A")
                
    # Update X and Y axes for cartesian charts
    try:
        fig_light.update_xaxes(
            linecolor="#CBD5E1",
            gridcolor="#F1F5F9",
            title_font=dict(color="#0F172A"),
            tickfont=dict(color="#334155")
        )
        fig_light.update_yaxes(
            linecolor="#CBD5E1",
            gridcolor="#F1F5F9",
            title_font=dict(color="#0F172A"),
            tickfont=dict(color="#334155")
        )
    except Exception:
        pass
    
    # Update indicator (gauge) traces
    try:
        fig_light.update_traces(
            selector=dict(type="indicator"),
            title_font=dict(color="#0F172A"),
            gauge_bgcolor="#F1F5F9",
            gauge_bordercolor="#CBD5E1",
            gauge_axis_tickcolor="#334155",
            gauge_axis_tickfont=dict(color="#334155"),
        )
    except Exception:
        pass
        
    return fig_light


class FinTwinPDFReport:
    """Builds a single professional, multi-page A4 PDF report."""

    def __init__(
        self,
        report_title: str,
        user_id: Optional[Union[str, int]] = None,
        report_id: Optional[str] = None,
        subtitle: Optional[str] = None,
    ):
        self.report_title = report_title
        self.user_id = user_id
        
        # Obfuscate user_id in report_id if it contains database user keys
        import hashlib
        if report_id:
            if user_id and isinstance(user_id, str) and user_id.startswith("user_"):
                anon_suffix = hashlib.md5(user_id.encode()).hexdigest()[:8].upper()
                self.report_id = report_id.replace(user_id, anon_suffix)
            else:
                self.report_id = report_id
        else:
            if user_id and isinstance(user_id, str) and user_id.startswith("user_"):
                anon_suffix = hashlib.md5(user_id.encode()).hexdigest()[:8].upper()
                self.report_id = f"FT-{anon_suffix}"
            else:
                self.report_id = f"FT-{user_id}" if user_id is not None else None
        
        self.subtitle = subtitle
        self.generated_at = datetime.now()
        self.styles = _build_styles()
        self.story: List[Any] = []
        self._build_cover()

    # ------------------------------------------------------------------ #
    # Cover block
    # ------------------------------------------------------------------ #
    def _build_cover(self):
        s = self.styles
        self.story.append(Spacer(1, 4 * mm))
        self.story.append(Paragraph(html.escape(self.report_title), s["CoverTitle"]))
        if self.subtitle:
            self.story.append(Paragraph(html.escape(self.subtitle), s["CoverSub"]))
        meta = f"Generated on {self.generated_at.strftime('%d %b %Y, %H:%M')}"
        if self.report_id:
            meta += f"   |   Report ID: {self.report_id}"
        self.story.append(Paragraph(meta, s["CoverSub"]))
        self.story.append(Spacer(1, 3 * mm))
        # Divider
        divider = Table([[""]], colWidths=[CONTENT_WIDTH], rowHeights=[1.4])
        divider.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND_PRIMARY)]))
        self.story.append(divider)
        self.story.append(Spacer(1, 5 * mm))

    # ------------------------------------------------------------------ #
    # Content builders
    # ------------------------------------------------------------------ #
    def add_section(self, title: str, level: int = 1):
        """Add a section/sub-section heading."""
        style = self.styles["H1"] if level == 1 else self.styles["H2"]
        clean_title = _clean_text_for_pdf(title, is_html=False)
        self.story.append(Paragraph(clean_title, style))

    def add_paragraph(self, text: str):
        if text is None or str(text).strip() == "":
            return
        safe = _clean_text_for_pdf(text)
        try:
            self.story.append(Paragraph(safe, self.styles["Body"]))
        except Exception:
            # Fallback to plain text without any tags
            plain = html.escape(re.sub(r'<[^>]+>', '', str(text)))
            self.story.append(Paragraph(plain, self.styles["Body"]))

    def add_spacer(self, height_mm: float = 3):
        self.story.append(Spacer(1, height_mm * mm))

    def add_page_break(self):
        self.story.append(PageBreak())

    def add_key_value_grid(self, data: Dict[str, Any], columns: int = 2):
        """Render a dict as a clean 2-column (label, value) styled grid."""
        if not data:
            return
        items = [(str(k).replace("_", " ").title(), _fmt_cell(v)) for k, v in data.items()]
        rows = []
        for i in range(0, len(items), columns):
            row = []
            for k, v in items[i : i + columns]:
                row.extend([k, v])
            while len(row) < columns * 2:
                row.extend(["", ""])
            rows.append(row)

        col_w = CONTENT_WIDTH / (columns * 2)
        widths = []
        for _ in range(columns):
            widths.extend([col_w * 0.85, col_w * 1.15])

        cell_style_label = ParagraphStyle(
            "kv_label", fontName="Helvetica-Bold", fontSize=8.4, textColor=BRAND_GREY
        )
        cell_style_val = ParagraphStyle(
            "kv_val", fontName="Helvetica-Bold", fontSize=9.2, textColor=BRAND_DARK
        )
        table_rows = []
        for row in rows:
            styled = []
            for idx, cell in enumerate(row):
                style = cell_style_label if idx % 2 == 0 else cell_style_val
                styled.append(Paragraph(str(cell), style) if cell != "" else "")
            table_rows.append(styled)

        t = Table(table_rows, colWidths=widths, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, BRAND_BORDER),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ]
            )
        )
        self.story.append(t)
        self.story.append(Spacer(1, 4 * mm))

    def add_dataframe_table(
        self,
        df: pd.DataFrame,
        title: Optional[str] = None,
        max_col_width_chars: int = 28,
    ):
        """Render a DataFrame as a professionally styled, auto-wrapping table
        that automatically continues across pages when it is long."""
        if df is None or df.empty:
            if title:
                self.add_section(title, level=2)
            self.add_paragraph("No data available for this section.")
            return

        if title:
            self.add_section(title, level=2)

        df = df.copy()
        # Drop columns that are entirely null/empty (per spec: only show sections with data)
        df = df.dropna(axis=1, how="all")
        if df.empty:
            self.add_paragraph("No data available for this section.")
            return

        headers = [str(c).replace("_", " ").title() for c in df.columns]
        header_style = self.styles["TableHeader"]
        cell_style = self.styles["TableCell"]

        data_rows = [[Paragraph(h, header_style) for h in headers]]
        for _, row in df.iterrows():
            data_rows.append([Paragraph(_fmt_cell(v), cell_style) for v in row.tolist()])

        n_cols = len(headers)
        
        # Calculate dynamic column widths based on cell content lengths
        col_widths_chars = []
        for col_idx in range(n_cols):
            max_len = len(headers[col_idx])
            for _, row in df.iterrows():
                val = row.iloc[col_idx]
                formatted_val = _fmt_cell(val)
                clean_val = re.sub(r'<[^>]*>', '', formatted_val)
                max_len = max(max_len, len(clean_val))
            # Cap max length to max_col_width_chars, minimum of 6 chars
            max_len = max(min(max_len, max_col_width_chars), 6)
            col_widths_chars.append(max_len)
            
        total_chars = sum(col_widths_chars)
        widths = [(w / total_chars) * CONTENT_WIDTH for w in col_widths_chars]
        
        t = Table(data_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(data_rows)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), BRAND_LIGHT_ROW))
        t.setStyle(TableStyle(style_cmds))
        self.story.append(t)
        self.story.append(Spacer(1, 5 * mm))

    def add_image_bytes(
        self,
        image_bytes: bytes,
        caption: Optional[str] = None,
        max_height_mm: float = 90,
    ):
        """Center an already-rendered image (PNG bytes), scaled to fit the
        page width/height without stretching, with an optional caption."""
        if not image_bytes:
            return
        try:
            img_reader = RLImage(io.BytesIO(image_bytes))
            iw, ih = img_reader.imageWidth, img_reader.imageHeight
            if not iw or not ih:
                return
            aspect = ih / float(iw)
            draw_w = CONTENT_WIDTH
            draw_h = draw_w * aspect
            max_h = max_height_mm * mm
            if draw_h > max_h:
                draw_h = max_h
                draw_w = draw_h / aspect
            img = RLImage(io.BytesIO(image_bytes), width=draw_w, height=draw_h)
            img.hAlign = "CENTER"
            block = [img]
            if caption:
                block.append(Paragraph(html.escape(caption), self.styles["Caption"]))
            self.story.append(KeepTogether(block))
        except Exception:
            self.add_paragraph(f"[Chart unavailable: {caption or 'image failed to render'}]")

    def add_plotly_figure(self, fig, caption: Optional[str] = None, scale: float = 2.0):
        """Render a Plotly go.Figure to high-resolution PNG (via kaleido) and
        embed it. Fails gracefully (with an inline note) if kaleido/plotly
        image export is unavailable, rather than breaking the whole report."""
        if fig is None:
            return
        try:
            fig_light = _convert_to_light_mode(fig)
            img_bytes = fig_light.to_image(format="png", scale=scale, engine="kaleido")
            self.add_image_bytes(img_bytes, caption=caption)
        except Exception as e:
            self.add_paragraph(
                f"[Chart '{caption or 'chart'}' could not be rendered: {e}]"
            )

    def add_matplotlib_figure(self, fig, caption: Optional[str] = None, dpi: int = 200):
        """Render a Matplotlib figure to high-resolution PNG and embed it."""
        if fig is None:
            return
        try:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
            buf.seek(0)
            self.add_image_bytes(buf.read(), caption=caption)
        except Exception as e:
            self.add_paragraph(
                f"[Chart '{caption or 'chart'}' could not be rendered: {e}]"
            )

    def add_disclaimer(self):
        """Append the mandatory AI disclaimer as the final block of content,
        so it naturally lands on the last page of the report."""
        self.story.append(Spacer(1, 6 * mm))
        self.story.append(Paragraph(html.escape(DISCLAIMER_TEXT), self.styles["Disclaimer"]))

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #
    def build(self) -> bytes:
        """Finalize the story (adding the disclaimer if not already present)
        and render the complete PDF, returning it as bytes."""
        if not self.story or DISCLAIMER_TEXT not in getattr(
            self.story[-1], "text", ""
        ):
            self.add_disclaimer()

        buf = io.BytesIO()
        ctx = {
            "report_title": self.report_title,
            "generated_at": self.generated_at.strftime("%d %b %Y, %H:%M"),
            "report_id": self.report_id,
        }

        def _make_canvas(*args, **kwargs):
            return _NumberedCanvas(*args, report_ctx=ctx, **kwargs)

        doc = BaseDocTemplate(
            buf,
            pagesize=PAGE_SIZE,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN + HEADER_RESERVE,
            bottomMargin=MARGIN + FOOTER_RESERVE,
            title=self.report_title,
            # author and creator are intentionally blank to avoid embedding
            # server-side application metadata in the PDF file properties.
            author="",
            creator="",
            subject="",
        )
        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id="main",
        )
        doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
        doc.build(self.story, canvasmaker=_make_canvas)
        return buf.getvalue()

    def suggested_filename(self, prefix: str) -> str:
        ts = self.generated_at.strftime("%Y-%m-%d_%H-%M-%S")
        safe_prefix = "".join(c for c in prefix if c.isalnum() or c in ("_", "-")) or "report"
        return f"FinTwinAI_{safe_prefix}_{ts}.pdf"
