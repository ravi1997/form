import logging
import io
from s3_helper import S3Helper
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger("PDFReceiptGenerator")

class PDFReceiptGenerator:
    @classmethod
    def generate_and_upload_receipt(cls, form_title, answers, response_id, theme_data=None):
        """
        Compiles the submission answers into a themed true PDF document using ReportLab and uploads it to S3.
        """
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=letter,
                rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
            )
            
            styles = getSampleStyleSheet()
            
            style_theme = {}
            if theme_data and "style" in theme_data:
                style_theme = theme_data["style"]
            
            primary_hex = style_theme.get("primary_color", "#00d2ff")
            text_hex = style_theme.get("text_color", "#333333")
            
            def get_color(hex_str, default=colors.black):
                try:
                    if hex_str.startswith("#"):
                        hex_str = hex_str[1:]
                    if len(hex_str) == 3:
                        hex_str = "".join([c*2 for c in hex_str])
                    r = int(hex_str[0:2], 16) / 255.0
                    g = int(hex_str[2:4], 16) / 255.0
                    b = int(hex_str[4:6], 16) / 255.0
                    return colors.Color(r, g, b)
                except Exception:
                    return default
            
            primary_color = get_color(primary_hex, colors.HexColor("#00d2ff"))
            text_color = get_color(text_hex, colors.HexColor("#333333"))
            
            title_style = ParagraphStyle(
                'ReceiptTitle',
                parent=styles['Heading1'],
                textColor=primary_color,
                fontSize=24,
                spaceAfter=15
            )
            
            meta_style = ParagraphStyle(
                'ReceiptMeta',
                parent=styles['Normal'],
                textColor=colors.gray,
                fontSize=10,
                spaceAfter=20
            )
            
            label_style = ParagraphStyle(
                'ReceiptLabel',
                parent=styles['Normal'],
                textColor=text_color,
                fontSize=10,
                fontName='Helvetica-Bold'
            )
            
            value_style = ParagraphStyle(
                'ReceiptValue',
                parent=styles['Normal'],
                textColor=text_color,
                fontSize=11,
                spaceAfter=10
            )
            
            story = []
            story.append(Paragraph("Submission Receipt", title_style))
            
            meta_text = f"<b>Form:</b> {form_title}<br/><b>Response ID:</b> {response_id}"
            story.append(Paragraph(meta_text, meta_style))
            story.append(Spacer(1, 10))
            
            for q_id, val in answers.items():
                story.append(Paragraph(str(q_id).upper(), label_style))
                story.append(Spacer(1, 4))
                story.append(Paragraph(str(val), value_style))
                story.append(Spacer(1, 10))
            
            doc.build(story)
            pdf_data = buffer.getvalue()
            buffer.close()
            
            filename = f"receipt_{response_id}.pdf"
            s3_url = S3Helper.upload_file(pdf_data, filename, content_type="application/pdf")
            logger.info(f"PDF Receipt uploaded successfully to S3: {s3_url}")
            return s3_url
        except Exception as e:
            logger.error(f"Failed to generate PDF receipt: {str(e)}")
            return None

# Backward compatibility alias
HTMLReceiptGenerator = PDFReceiptGenerator
