import logging
from s3_helper import S3Helper

logger = logging.getLogger("PDFGenerator")

class PDFGenerator:
    @classmethod
    def generate_and_upload_receipt(cls, form_title, answers, response_id, theme_data=None):
        """
        Compiles the submission answers into a beautifully themed receipt document and uploads it to S3.
        """
        try:
            # Extract styling properties
            style = {}
            if theme_data and "style" in theme_data:
                style = theme_data["style"]
            
            font_family = style.get("font_family", "sans-serif")
            primary_color = style.get("primary_color", "#00d2ff")
            surface_color = style.get("surface_color", "#ffffff")
            text_color = style.get("text_color", "#333333")
            border_radius = style.get("border_radius", "6px")
            input_bordercolor = style.get("input_bordercolor", "#eeeeee")
            input_backcolor = style.get("input_backcolor", "#f9f9f9")

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: {font_family}; 
                        padding: 40px; 
                        color: {text_color}; 
                        background-color: {surface_color}; 
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        border: 1px solid {input_bordercolor};
                        border-radius: {border_radius};
                        padding: 30px;
                        background: {surface_color};
                        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                    }}
                    h1 {{ 
                        color: {primary_color}; 
                        border-bottom: 2px solid {primary_color}; 
                        padding-bottom: 10px; 
                        margin-top: 0;
                    }}
                    .meta {{ 
                        color: #777; 
                        margin-bottom: 30px; 
                        font-size: 0.9em;
                        border-bottom: 1px dashed {input_bordercolor};
                        padding-bottom: 15px;
                    }}
                    .item {{ 
                        margin-bottom: 20px; 
                        padding: 15px; 
                        background: {input_backcolor}; 
                        border: 1px solid {input_bordercolor};
                        border-radius: {border_radius}; 
                    }}
                    .label {{ 
                        font-weight: bold; 
                        color: {text_color}; 
                        opacity: 0.8;
                        font-size: 0.85em;
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                    }}
                    .value {{ 
                        margin-top: 8px; 
                        font-size: 1.05em;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Submission Receipt</h1>
                    <div class="meta">
                        <p><strong>Form:</strong> {form_title}</p>
                        <p><strong>Response ID:</strong> {response_id}</p>
                    </div>
                    <div>
            """
            for q_id, val in answers.items():
                html_content += f"""
                <div class="item">
                    <div class="label">{q_id}</div>
                    <div class="value">{val}</div>
                </div>
                """
            
            html_content += """
                    </div>
                </div>
            </body>
            </html>
            """
            
            filename = f"receipt_{response_id}.html"
            s3_url = S3Helper.upload_file(html_content.encode("utf-8"), filename, content_type="text/html")
            logger.info(f"Receipt uploaded successfully to S3: {s3_url}")
            return s3_url
        except Exception as e:
            logger.error(f"Failed to generate receipt: {str(e)}")
            return None
