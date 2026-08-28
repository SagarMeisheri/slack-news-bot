"""
Sarvam Document Intelligence JSON-to-Markdown and HTML Table Parser.
Converts Sarvam Vision 1.5 AST output (pages, layout_tags, coordinates, HTML tables)
into clean GitHub Markdown with table formatting and saves raw JSON artifacts.
"""

import html
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

logger = logging.getLogger("sarvam_parser")


def convert_html_table_to_markdown(html_table_str: str) -> str:
    """
    Converts an HTML <table> string into a GitHub-compatible Markdown table.
    Handles <thead>, <tbody>, <tfoot>, <th>, <td>, <br/>, and rowspans/colspans gracefully.
    """
    if not html_table_str or "<table" not in html_table_str:
        return html_table_str

    try:
        # Pre-process HTML tags for XML parsing (replace <br/> with space, clean unclosed tags)
        cleaned_html = re.sub(r"<br\s*/?>", " ", html_table_str, flags=re.IGNORECASE)
        cleaned_html = html.unescape(cleaned_html)
        
        # Ensure it's wrapped in root if necessary
        wrapped_xml = f"<root>{cleaned_html}</root>"
        root = ET.fromstring(wrapped_xml)
        
        table_elem = root.find(".//table")
        if table_elem is None:
            return html_table_str

        rows: List[List[str]] = []

        # Find all tr elements anywhere in table (thead, tbody, tfoot, or direct)
        for tr in table_elem.findall(".//tr"):
            row_cells: List[str] = []
            for cell in tr:
                if cell.tag.lower() in ("th", "td"):
                    # Get all inner text recursively
                    cell_text = "".join(cell.itertext()).strip()
                    # Clean newlines and pipes
                    cell_text = re.sub(r"\s+", " ", cell_text).replace("|", "&#124;")
                    
                    # Check for colspan to replicate columns
                    colspan = int(cell.attrib.get("colspan", 1)) if cell.attrib.get("colspan", "").isdigit() else 1
                    row_cells.append(cell_text)
                    for _ in range(colspan - 1):
                        row_cells.append("")
            
            if any(c for c in row_cells):  # Only add non-empty rows
                rows.append(row_cells)

        if not rows:
            return html_table_str

        # Normalize column count across all rows
        max_cols = max(len(r) for r in rows)
        if max_cols == 0:
            return html_table_str

        for r in rows:
            while len(r) < max_cols:
                r.append("")

        # Construct Markdown Table
        header_row = rows[0]
        md_lines: List[str] = [
            "| " + " | ".join(c if c else " " for c in header_row) + " |",
            "| " + " | ".join("---" for _ in range(max_cols)) + " |",
        ]

        for data_row in rows[1:]:
            md_lines.append("| " + " | ".join(c if c else " " for c in data_row) + " |")

        return "\n" + "\n".join(md_lines) + "\n"

    except Exception as e:
        logger.debug(f"HTML table parsing fallback: {e}")
        # Regex-based fallback for messy HTML
        return _regex_fallback_table_converter(html_table_str)


def _regex_fallback_table_converter(html_table_str: str) -> str:
    """Fallback regex converter if XML parsing fails."""
    try:
        tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", html_table_str, flags=re.DOTALL | re.IGNORECASE)
        if not tr_matches:
            # Strip tags and return text
            return re.sub(r"<[^>]+>", " ", html_table_str).strip()

        rows: List[List[str]] = []
        for tr in tr_matches:
            cells = re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", tr, flags=re.DOTALL | re.IGNORECASE)
            cleaned_cells = [re.sub(r"<[^>]+>", " ", c).strip().replace("|", "&#124;") for c in cells]
            if any(cleaned_cells):
                rows.append(cleaned_cells)

        if not rows:
            return re.sub(r"<[^>]+>", " ", html_table_str).strip()

        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        md_lines = [
            "| " + " | ".join(c if c else " " for c in rows[0]) + " |",
            "| " + " | ".join("---" for _ in range(max_cols)) + " |",
        ]
        for data_row in rows[1:]:
            md_lines.append("| " + " | ".join(c if c else " " for c in data_row) + " |")

        return "\n" + "\n".join(md_lines) + "\n"
    except Exception:
        return re.sub(r"<[^>]+>", " ", html_table_str).strip()


def parse_sarvam_output_to_markdown(data: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Parses Sarvam Document Intelligence JSON output into rich, readable Markdown.
    
    Returns:
        (formatted_markdown, document_metadata)
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return data, {"total_pages": 1, "table_count": 0}

    if not isinstance(data, dict):
        return str(data), {"total_pages": 1, "table_count": 0}

    # Direct markdown or text field
    if "markdown" in data and isinstance(data["markdown"], str):
        return data["markdown"], {"total_pages": 1, "table_count": 0}

    documents = data.get("documents", [])
    if not documents:
        # Check for results list
        results = data.get("results")
        if isinstance(results, list):
            md_parts = [r.get("content", str(r)) for r in results if isinstance(r, dict)]
            return "\n\n---\n\n".join(md_parts), {"total_pages": len(results), "table_count": 0}
        return json.dumps(data, indent=2), {"total_pages": 1, "table_count": 0}

    md_pages: List[str] = []
    total_tables = 0
    total_pages = len(documents[0].get("pages", [])) if documents else 1
    doc_filename = documents[0].get("filename", "document.pdf") if documents else "document.pdf"

    for doc in documents:
        pages = doc.get("pages", [])
        for p in pages:
            page_num = p.get("page_num", 1)
            blocks = p.get("blocks", [])
            
            # Sort by reading order if available
            sorted_blocks = sorted(blocks, key=lambda b: b.get("reading_order", 0))
            
            page_elements: List[str] = []
            page_elements.append(f"## Page {page_num}\n")

            for b in sorted_blocks:
                tag = b.get("layout_tag", "paragraph").lower()
                text = (b.get("text") or "").strip()
                if not text:
                    continue

                if tag == "table":
                    total_tables += 1
                    md_table = convert_html_table_to_markdown(text)
                    page_elements.append(md_table)

                elif tag in ("header", "section-title"):
                    page_elements.append(f"### {text}\n")

                elif tag == "footer":
                    page_elements.append(f"_{text}_\n")

                elif tag == "image":
                    # Filter out verbose AI descriptions of small UI icons (e.g. phone/laptop icons)
                    lower_t = text.lower()
                    if any(w in lower_t for w in ("icon", "simple stylized", "not a chart or graph", "logo consists", "pill-shaped")):
                        continue  # Skip verbose icon descriptions
                    else:
                        page_elements.append(f"> 🖼️ **Image/Chart:** _{text}_\n")

                else:  # Standard paragraph
                    page_elements.append(f"{text}\n")

            md_pages.append("\n".join(page_elements))

    full_markdown = "\n\n---\n\n".join(md_pages)
    
    metadata = {
        "job_id": data.get("job_id"),
        "filename": doc_filename,
        "total_pages": total_pages,
        "table_count": total_tables,
        "status": data.get("status", "completed"),
    }

    return full_markdown, metadata


def save_ocr_artifacts(
    raw_data: Any,
    markdown_content: str,
    filename: str,
    output_dir: str = "saved_reports",
) -> Tuple[str, str]:
    """
    Saves the complete raw JSON and formatted Markdown files to disk.
    Returns (json_filepath, md_filepath).
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_stem = re.sub(r"[^\w\-]", "_", filename.rsplit(".", 1)[0])
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    json_filename = f"ocr_{clean_stem}_{timestamp}.json"
    md_filename = f"ocr_{clean_stem}_{timestamp}.md"

    json_path = os.path.join(output_dir, json_filename)
    md_path = os.path.join(output_dir, md_filename)

    with open(json_path, "w", encoding="utf-8") as f:
        if isinstance(raw_data, (dict, list)):
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        else:
            f.write(str(raw_data))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    logger.info(f"Saved OCR artifacts: JSON -> {json_path}, MD -> {md_path}")
    return json_path, md_path
