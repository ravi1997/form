"""
exporter.py
-----------
Export analysis results to CSV or PDF.

CSV: each step gets its own section; crosstab is a proper 2D grid.
PDF: formatted report using reportlab with a professional table style.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone


# ===========================================================================
# CSV Export
# ===========================================================================

def export_to_csv(analysis_result: dict) -> bytes:
    """Convert a full analysis result into a CSV file (UTF-8 bytes)."""
    output = io.StringIO()
    writer = csv.writer(output)

    # --- Metadata header ---
    writer.writerow(["Analysis Name", analysis_result.get("name", "")])
    writer.writerow(["Description", analysis_result.get("description", "")])
    writer.writerow(["Source Collection", analysis_result.get("source_collection", "")])
    writer.writerow(["Total Matching Responses", analysis_result.get("total_matching_responses", "")])
    writer.writerow(["Exported At", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])

    for step_id, step_result in analysis_result.get("results", {}).items():
        _write_step_csv(writer, step_id, step_result, indent=0)
        writer.writerow([])

    return output.getvalue().encode("utf-8-sig")   # UTF-8 BOM for Excel compatibility


def stream_csv_generator(analysis_result: dict):
    """Generator yielding CSV rows one by one (to stream to the HTTP response)."""
    class StringQueue:
        def __init__(self):
            self.lines = []
        def write(self, s):
            self.lines.append(s)
        def flush(self):
            pass
        def get_and_clear(self):
            res = "".join(self.lines)
            self.lines = []
            return res

    queue = StringQueue()
    writer = csv.writer(queue)

    writer.writerow(["Analysis Name", analysis_result.get("name", "")])
    yield queue.get_and_clear().encode("utf-8-sig")  # BOM first

    writer.writerow(["Description", analysis_result.get("description", "")])
    writer.writerow(["Source Collection", analysis_result.get("source_collection", "")])
    writer.writerow(["Total Matching Responses", analysis_result.get("total_matching_responses", "")])
    writer.writerow(["Exported At", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])
    yield queue.get_and_clear().encode("utf-8")

    for step_id, step_result in analysis_result.get("results", {}).items():
        _write_step_csv(writer, step_id, step_result, indent=0)
        writer.writerow([])
        yield queue.get_and_clear().encode("utf-8")



def _write_step_csv(writer, step_id: str, step_result: dict, indent: int = 0):
    prefix = "  " * indent
    step_type = step_result.get("type", "unknown")
    label = step_result.get("label", step_id)

    writer.writerow([f"{prefix}[{step_type.upper()}] {label}"])

    if step_type == "frequency":
        writer.writerow([f"{prefix}Value", "Count", "Percentage (%)"])
        for row in step_result.get("breakdown", []):
            writer.writerow([f"{prefix}{row.get('value')}", row.get("count"), row.get("percentage")])
        writer.writerow([f"{prefix}TOTAL", step_result.get("total_responses", ""), 100])

    elif step_type == "aggregate":
        result_val = step_result.get("result")
        if isinstance(result_val, float):
            result_val = round(result_val, 4)
        writer.writerow([f"{prefix}Operation", "Field", "Result"])
        writer.writerow([
            f"{prefix}{step_result.get('operation', '').upper()}",
            step_result.get("field"),
            result_val,
        ])

    elif step_type == "crosstab":
        columns = step_result.get("columns", [])
        writer.writerow([f"{prefix}↓ Row \\ Col →"] + columns + ["Row Total"])
        for row in step_result.get("rows", []):
            cells = [f"{prefix}{row.get('_row', '')}"]
            cells += [row.get(str(c), 0) for c in columns]
            cells.append(row.get("_total", 0))
            writer.writerow(cells)

    elif step_type == "top_n":
        writer.writerow([f"{prefix}Rank", "Value", "Count", "Percentage (%)"])
        for i, row in enumerate(step_result.get("top", []), 1):
            writer.writerow([f"{prefix}{i}", row.get("value"), row.get("count"), row.get("percentage")])

    elif step_type == "missing":
        writer.writerow([f"{prefix}Metric", "Count", "Percentage (%)"])
        writer.writerow([f"{prefix}Missing", step_result.get("missing"), f"{step_result.get('missing_pct', 0):.1f}%"])
        writer.writerow([f"{prefix}Filled",  step_result.get("filled"),  f"{step_result.get('filled_pct', 0):.1f}%"])
        writer.writerow([f"{prefix}Total",   step_result.get("total_responses", 0), "100%"])

    elif step_type == "array_frequency":
        writer.writerow([f"{prefix}Responses with data: {step_result.get('response_count', 0)}"])
        writer.writerow([f"{prefix}Total selections: {step_result.get('total_selections', 0)}"])
        writer.writerow([f"{prefix}Avg selections/response: {step_result.get('avg_selections_per_response', 0)}"])
        writer.writerow([
            f"{prefix}Option", "Count",
            "% of Selections", "% of Responses",
        ])
        for row in step_result.get("breakdown", []):
            writer.writerow([
                f"{prefix}{row.get('value')}",
                row.get("count"),
                f"{row.get('percentage_of_selections', 0):.1f}%",
                f"{row.get('percentage_of_responses', 0):.1f}%",
            ])

    elif step_type == "summarize":
        writer.writerow([f"{prefix}Metric", "Value"])
        writer.writerow([f"{prefix}Observations", step_result.get("count")])
        writer.writerow([f"{prefix}Mean", step_result.get("mean")])
        writer.writerow([f"{prefix}Std. Dev.", step_result.get("std_dev")])
        writer.writerow([f"{prefix}Variance", step_result.get("variance")])
        writer.writerow([f"{prefix}Skewness", step_result.get("skewness")])
        writer.writerow([f"{prefix}Kurtosis", step_result.get("kurtosis")])
        writer.writerow([f"{prefix}Min", step_result.get("min")])
        writer.writerow([f"{prefix}Max", step_result.get("max")])
        for p, val in sorted(step_result.get("percentiles", {}).items(), key=lambda x: int(x[0][1:]) if x[0].startswith("p") else int(x[0])):
            writer.writerow([f"{prefix}p{p}", val])

    elif step_type == "tabulate_chi2":
        columns = step_result.get("columns", [])
        writer.writerow([f"{prefix}↓ Row \\ Col →"] + columns + ["Row Total"])
        for row in step_result.get("rows", []):
            cells = [f"{prefix}{row.get('_row', '')}"]
            cells += [row.get(str(c), 0) for c in columns]
            cells.append(row.get("_total", 0))
            writer.writerow(cells)
        chi2 = step_result.get("chi2", {})
        writer.writerow([f"{prefix}Pearson chi2({chi2.get('df')})", chi2.get("statistic"), f"p-value = {chi2.get('p_value')}"])

    elif step_type == "regress":
        writer.writerow([f"{prefix}Observations", step_result.get("observations")])
        writer.writerow([f"{prefix}R-squared", step_result.get("r_squared")])
        writer.writerow([f"{prefix}Adj R-squared", step_result.get("adj_r_squared")])
        writer.writerow([f"{prefix}F-statistic", step_result.get("f_statistic")])
        writer.writerow([f"{prefix}Prob > F", step_result.get("f_p_value")])
        writer.writerow([f"{prefix}Variable", "Coefficient", "Std. Err.", "t", "P>|t|"])
        for var, details in step_result.get("coefficients", {}).items():
            if var == "slope":
                continue
            writer.writerow([f"{prefix}{var}", details.get("coef"), details.get("std_err"), details.get("t_stat"), details.get("p_value")])
        if "hettest" in step_result:
            het = step_result["hettest"]
            writer.writerow([f"{prefix}Breusch-Pagan test for heteroskedasticity:"])
            writer.writerow([f"{prefix}chi2({het.get('df')})", het.get("lm_statistic"), f"Prob > chi2 = {het.get('p_value')}"])

    elif step_type == "ttest":
        writer.writerow([f"{prefix}Group", "Obs", "Mean", "Std. Dev.", "Std. Err."])
        for gp, details in sorted(step_result.get("groups", {}).items()):
            writer.writerow([f"{prefix}{gp}", details.get("obs"), details.get("mean"), details.get("std_dev"), details.get("std_err")])
        welch = step_result.get("welch_ttest", {})
        writer.writerow([f"{prefix}t-statistic", welch.get("statistic")])
        writer.writerow([f"{prefix}df", welch.get("df")])
        writer.writerow([f"{prefix}Prob > |t|", welch.get("p_value")])

    elif step_type == "pwcorr":
        fields = step_result.get("fields", [])
        writer.writerow([f"{prefix}Correlation Matrix"])
        writer.writerow([f"{prefix}Variable"] + fields)
        for f1 in fields:
            row = [f"{prefix}{f1}"]
            for f2 in fields:
                cell = step_result["matrix"][f1].get(f2, {})
                coef = cell.get("coef")
                p_val = cell.get("p_value")
                if coef is None:
                    row.append("-")
                elif p_val is not None:
                    row.append(f"{coef:.4f} ({p_val:.4f})")
                else:
                    row.append(f"{coef:.4f}")
            writer.writerow(row)

    elif step_type == "tabstat":
        results = step_result.get("results", {})
        if results:
            first_group = next(iter(results.values()))
            first_field = next(iter(first_group.values()))
            stats_keys = list(first_field.keys())
            writer.writerow([f"{prefix}Group", "Variable"] + stats_keys)
            for group, fields_data in sorted(results.items()):
                for f, stats in sorted(fields_data.items()):
                    row = [f"{prefix}{group}", f]
                    for sk in stats_keys:
                        row.append(stats.get(sk))
                    writer.writerow(row)

    elif step_type == "codebook":
        for f, details in sorted(step_result.get("fields", {}).items()):
            writer.writerow([f"{prefix}Field", f])
            writer.writerow([f"{prefix}Type", details.get("data_type")])
            writer.writerow([f"{prefix}Obs", details.get("obs")])
            writer.writerow([f"{prefix}Missing", details.get("missing")])
            writer.writerow([f"{prefix}Unique", details.get("unique")])
            if "numeric_stats" in details:
                num = details["numeric_stats"]
                writer.writerow([f"{prefix}Mean", num.get("mean")])
                writer.writerow([f"{prefix}Std. Dev.", num.get("std_dev")])
                writer.writerow([f"{prefix}Min", num.get("min")])
                writer.writerow([f"{prefix}Max", num.get("max")])
            if "frequencies" in details:
                writer.writerow([f"{prefix}Frequencies:"])
                for freq in details["frequencies"]:
                    writer.writerow([f"{prefix}  {freq['value']}", freq['count'], f"{freq['percent']}%"])

    elif step_type == "oneway_anova":
        table = step_result.get("anova_table", {})
        writer.writerow([f"{prefix}Source", "SS", "df", "MS"])
        for src in ["between", "within", "total"]:
            s_data = table.get(src, {})
            writer.writerow([f"{prefix}{src.upper()}", s_data.get("ss"), s_data.get("df"), s_data.get("ms", "")])
        writer.writerow([f"{prefix}F-statistic", step_result.get("f_statistic")])
        writer.writerow([f"{prefix}Prob > F", step_result.get("p_value")])

    elif step_type == "transform":
        writer.writerow([f"{prefix}Status", step_result.get("status")])
        writer.writerow([f"{prefix}Target Field", "Operation", "Source Field"])
        for t in step_result.get("transformations", []):
            writer.writerow([f"{prefix}{t.get('field')}", t.get('operation'), t.get('source_field')])

    elif step_type == "segment":
        writer.writerow([f"{prefix}Segment size: {step_result.get('segment_count', 0)} responses"])
        for sub_id, sub_result in step_result.get("sub_results", {}).items():
            _write_step_csv(writer, sub_id, sub_result, indent=indent + 1)


# ===========================================================================
# PDF Export
# ===========================================================================

def export_to_pdf(analysis_result: dict) -> bytes:
    """Convert a full analysis result into a formatted PDF (bytes)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable,
        )
    except ImportError:
        raise RuntimeError("reportlab is required for PDF export. Run: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    styles = getSampleStyleSheet()

    DARK_BLUE = colors.HexColor("#1e3a5f")
    MID_BLUE  = colors.HexColor("#2c5282")
    LIGHT_BLUE = colors.HexColor("#ebf8ff")
    BORDER    = colors.HexColor("#bee3f8")
    GREY_TEXT = colors.HexColor("#555555")

    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=20, textColor=DARK_BLUE, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=GREY_TEXT, spaceAfter=2,
    )
    step_heading_style = ParagraphStyle(
        "StepHeading", parent=styles["Heading2"],
        fontSize=13, textColor=MID_BLUE, spaceBefore=14, spaceAfter=4,
    )
    sub_heading_style = ParagraphStyle(
        "SubHeading", parent=styles["Heading3"],
        fontSize=11, textColor=MID_BLUE, spaceBefore=8, spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        "Meta", parent=styles["Normal"],
        fontSize=9, textColor=GREY_TEXT,
    )
    body_style = styles["Normal"]

    def _table(data: list[list], col_widths=None) -> Table:
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            # Header
            ("BACKGROUND",    (0, 0), (-1, 0), MID_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            # Body
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LIGHT_BLUE]),
            ("ALIGN",         (1, 1), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
            # Grid
            ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]))
        return t

    # ------------------------------------------------------------------
    # Build story
    # ------------------------------------------------------------------
    story = []

    story.append(Paragraph(analysis_result.get("name", "Analysis Report"), title_style))
    if analysis_result.get("description"):
        story.append(Paragraph(analysis_result["description"], subtitle_style))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        f"Total matching responses: <b>{analysis_result.get('total_matching_responses', 0)}</b> &nbsp;&nbsp;|&nbsp;&nbsp;"
        f"Generated: <b>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</b>",
        meta_style,
    ))

    filters = analysis_result.get("filters_applied", [])
    if filters:
        filter_strs = [f"{f['field']} {f['operator']} {f['value']}" for f in filters]
        story.append(Paragraph("Filters: " + " | ".join(filter_strs), meta_style))

    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE, spaceAfter=10))

    for step_id, step_result in analysis_result.get("results", {}).items():
        _write_step_pdf(story, step_id, step_result,
                        step_heading_style, sub_heading_style,
                        body_style, meta_style, _table, Spacer, cm)

    doc.build(story)
    return buffer.getvalue()


def _write_step_pdf(story, step_id, step_result,
                    heading_style, sub_heading_style,
                    body_style, meta_style, make_table, Spacer, cm,
                    is_sub: bool = False):
    from reportlab.platypus import Paragraph as P

    step_type = step_result.get("type", "unknown")
    label = step_result.get("label", step_id)
    h_style = sub_heading_style if is_sub else heading_style

    story.append(P(label, h_style))

    if step_type == "frequency":
        total = step_result.get("total_responses", 0)
        story.append(P(f"Total responses in scope: {total}", meta_style))
        data = [["Value", "Count", "Percentage (%)"]]
        for row in step_result.get("breakdown", []):
            data.append([
                str(row.get("value", "")),
                str(row.get("count", 0)),
                f"{row.get('percentage', 0):.1f}%",
            ])
        if len(data) > 1:
            story.append(make_table(data))

    elif step_type == "aggregate":
        val = step_result.get("result")
        if isinstance(val, float):
            val = f"{val:.4f}"
        story.append(P(
            f"<b>{str(step_result.get('operation', '')).upper()}</b> "
            f"of <i>{step_result.get('field', '')}</i>: <b>{val}</b>",
            body_style,
        ))

    elif step_type == "crosstab":
        cols = step_result.get("columns", [])
        data = [[""] + [str(c) for c in cols] + ["Total"]]
        for row in step_result.get("rows", []):
            r = [str(row.get("_row", ""))]
            r += [str(row.get(str(c), 0)) for c in cols]
            r.append(str(row.get("_total", 0)))
            data.append(r)
        if len(data) > 1:
            story.append(make_table(data))

    elif step_type == "top_n":
        total = step_result.get("total_responses", 0)
        story.append(P(f"Out of {total} responses:", meta_style))
        data = [["Rank", "Value", "Count", "Percentage (%)"]]
        for i, row in enumerate(step_result.get("top", []), 1):
            data.append([
                str(i),
                str(row.get("value", "")),
                str(row.get("count", 0)),
                f"{row.get('percentage', 0):.1f}%",
            ])
        if len(data) > 1:
            story.append(make_table(data))

    elif step_type == "missing":
        data = [
            ["Metric",   "Count",  "Percentage (%)"],
            ["Missing",  str(step_result.get("missing", 0)),  f"{step_result.get('missing_pct', 0):.1f}%"],
            ["Filled",   str(step_result.get("filled",  0)),  f"{step_result.get('filled_pct',  0):.1f}%"],
            ["Total",    str(step_result.get("total_responses", 0)), "100%"],
        ]
        story.append(make_table(data))

    elif step_type == "array_frequency":
        resp  = step_result.get("response_count", 0)
        total = step_result.get("total_selections", 0)
        avg   = step_result.get("avg_selections_per_response", 0)
        story.append(P(
            f"Responses answered: <b>{resp}</b> &nbsp;|&nbsp; "
            f"Total selections: <b>{total}</b> &nbsp;|&nbsp; "
            f"Avg per response: <b>{avg}</b>",
            meta_style,
        ))
        data = [["Option", "Count", "% of Selections", "% of Responses"]]
        for row in step_result.get("breakdown", []):
            data.append([
                str(row.get("value", "")),
                str(row.get("count", 0)),
                f"{row.get('percentage_of_selections', 0):.1f}%",
                f"{row.get('percentage_of_responses', 0):.1f}%",
            ])
        if len(data) > 1:
            story.append(make_table(data))

    elif step_type == "summarize":
        data = [
            ["Metric", "Value"],
            ["Observations", str(step_result.get("count", 0))],
            ["Mean", f"{step_result.get('mean', 0):.4f}" if step_result.get("mean") is not None else ""],
            ["Std. Dev.", f"{step_result.get('std_dev', 0):.4f}" if step_result.get("std_dev") is not None else ""],
            ["Variance", f"{step_result.get('variance', 0):.4f}" if step_result.get("variance") is not None else ""],
            ["Skewness", f"{step_result.get('skewness', 0):.4f}" if step_result.get("skewness") is not None else ""],
            ["Kurtosis", f"{step_result.get('kurtosis', 0):.4f}" if step_result.get("kurtosis") is not None else ""],
            ["Min", str(step_result.get("min", ""))],
            ["Max", str(step_result.get("max", ""))]
        ]
        for p, val in sorted(step_result.get("percentiles", {}).items(), key=lambda x: int(x[0][1:]) if x[0].startswith("p") else int(x[0])):
            data.append([f"p{p} Percentile", f"{val:.4f}"])
        story.append(make_table(data))

    elif step_type == "tabulate_chi2":
        cols = step_result.get("columns", [])
        data = [[""] + [str(c) for c in cols] + ["Total"]]
        for row in step_result.get("rows", []):
            r = [str(row.get("_row", ""))]
            r += [str(row.get(str(c), 0)) for c in cols]
            r.append(str(row.get("_total", 0)))
            data.append(r)
        if len(data) > 1:
            story.append(make_table(data))
        chi2 = step_result.get("chi2", {})
        story.append(P(f"Pearson chi2({chi2.get('df')}) = <b>{chi2.get('statistic', 0):.4f}</b> &nbsp;&nbsp; p-value = <b>{chi2.get('p_value', 0):.6f}</b>", meta_style))

    elif step_type == "regress":
        story.append(P(f"Number of obs = <b>{step_result.get('observations')}</b> &nbsp;&nbsp;|&nbsp;&nbsp; R-squared = <b>{step_result.get('r_squared', 0):.4f}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Adj R-squared = <b>{step_result.get('adj_r_squared', 0):.4f}</b>", meta_style))
        story.append(P(f"F-statistic = <b>{step_result.get('f_statistic', 0):.4f}</b> &nbsp;&nbsp; Prob > F = <b>{step_result.get('f_p_value', 0):.6f}</b>", meta_style))
        data = [["Variable", "Coef.", "Std. Err.", "t", "P>|t|"]]
        for var, details in step_result.get("coefficients", {}).items():
            if var == "slope":
                continue
            data.append([
                str(var),
                f"{details.get('coef', 0):.4f}",
                f"{details.get('std_err', 0):.4f}",
                f"{details.get('t_stat', 0):.2f}",
                f"{details.get('p_value', 0):.6f}"
            ])
        story.append(make_table(data))
        if "hettest" in step_result:
            het = step_result["hettest"]
            story.append(P(f"<b>Breusch-Pagan test for heteroskedasticity:</b> chi2({het.get('df')}) = <b>{het.get('lm_statistic', 0):.4f}</b> &nbsp;&nbsp; Prob > chi2 = <b>{het.get('p_value', 0):.6f}</b>", meta_style))

    elif step_type == "ttest":
        data = [["Group", "Obs", "Mean", "Std. Dev.", "Std. Err."]]
        for gp, details in sorted(step_result.get("groups", {}).items()):
            data.append([
                str(gp),
                str(details.get("obs")),
                f"{details.get('mean', 0):.4f}",
                f"{details.get('std_dev', 0):.4f}",
                f"{details.get('std_err', 0):.4f}"
            ])
        story.append(make_table(data))
        welch = step_result.get("welch_ttest", {})
        story.append(P(f"t-statistic = <b>{welch.get('statistic', 0):.4f}</b> &nbsp;&nbsp; df = <b>{welch.get('df', 0):.2f}</b> &nbsp;&nbsp; Prob > |t| = <b>{welch.get('p_value', 0):.6f}</b>", meta_style))

    elif step_type == "pwcorr":
        fields = step_result.get("fields", [])
        data = [["Variable"] + fields]
        for f1 in fields:
            row = [str(f1)]
            for f2 in fields:
                cell = step_result["matrix"][f1].get(f2, {})
                coef = cell.get("coef")
                p_val = cell.get("p_value")
                if coef is None:
                    row.append("-")
                elif p_val is not None:
                    row.append(f"{coef:.4f}\n({p_val:.4f})")
                else:
                    row.append(f"{coef:.4f}")
            data.append(row)
        story.append(make_table(data))

    elif step_type == "tabstat":
        results = step_result.get("results", {})
        if results:
            first_group = next(iter(results.values()))
            first_field = next(iter(first_group.values()))
            stats_keys = list(first_field.keys())
            data = [["Group", "Variable"] + stats_keys]
            for group, fields_data in sorted(results.items()):
                for f, stats in sorted(fields_data.items()):
                    row = [str(group), str(f)]
                    for sk in stats_keys:
                        row.append(str(stats.get(sk)))
                    data.append(row)
            story.append(make_table(data))

    elif step_type == "codebook":
        for f, details in sorted(step_result.get("fields", {}).items()):
            story.append(P(f"<b>Field: {f}</b> (Type: {details.get('data_type')})", sub_heading_style))
            desc_str = f"Obs: <b>{details.get('obs')}</b> &nbsp;|&nbsp; Missing: <b>{details.get('missing')}</b> &nbsp;|&nbsp; Unique: <b>{details.get('unique')}</b>"
            story.append(P(desc_str, meta_style))
            if "numeric_stats" in details:
                num = details["numeric_stats"]
                p_str = " | ".join(f"p{k}: {v:.2f}" for k, v in num.get("percentiles", {}).items())
                num_str = f"Mean: <b>{num.get('mean')}</b> &nbsp;|&nbsp; Std. Dev.: <b>{num.get('std_dev')}</b> &nbsp;|&nbsp; Min: <b>{num.get('min')}</b> &nbsp;|&nbsp; Max: <b>{num.get('max')}</b><br/>Percentiles: {p_str}"
                story.append(P(num_str, body_style))
            if "frequencies" in details:
                freq_data = [["Value", "Count", "Percent"]]
                for freq in details["frequencies"]:
                    freq_data.append([str(freq["value"]), str(freq["count"]), f"{freq['percent']}%"])
                if len(freq_data) > 1:
                    story.append(make_table(freq_data))
            story.append(Spacer(1, 0.1 * cm))

    elif step_type == "oneway_anova":
        table = step_result.get("anova_table", {})
        data = [
            ["Source", "SS", "df", "MS"],
            ["Between Groups", str(table.get("between", {}).get("ss", 0)), str(table.get("between", {}).get("df", 0)), str(table.get("between", {}).get("ms", 0))],
            ["Within Groups", str(table.get("within", {}).get("ss", 0)), str(table.get("within", {}).get("df", 0)), str(table.get("within", {}).get("ms", 0))],
            ["Total", str(table.get("total", {}).get("ss", 0)), str(table.get("total", {}).get("df", 0)), ""]
        ]
        story.append(make_table(data))
        story.append(P(f"F-statistic({table.get('between', {}).get('df')}, {table.get('within', {}).get('df')}) = <b>{step_result.get('f_statistic', 0):.4f}</b> &nbsp;&nbsp; Prob > F = <b>{step_result.get('p_value', 0):.6f}</b>", meta_style))

    elif step_type == "transform":
        story.append(P(f"Status: <b>{step_result.get('status')}</b>", meta_style))
        data = [["Target Field", "Operation", "Source Field"]]
        for t in step_result.get("transformations", []):
            data.append([str(t.get("field")), str(t.get("operation")), str(t.get("source_field"))])
        if len(data) > 1:
            story.append(make_table(data))

    elif step_type == "segment":
        story.append(P(f"Segment size: <b>{step_result.get('segment_count', 0)}</b> responses", meta_style))
        for sub_id, sub_result in step_result.get("sub_results", {}).items():
            _write_step_pdf(story, sub_id, sub_result,
                            heading_style, sub_heading_style,
                            body_style, meta_style, make_table,
                            Spacer, cm, is_sub=True)

    story.append(Spacer(1, 0.2 * cm))
