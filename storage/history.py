"""
History and Persistence Manager for Search Reports.
Stores executed IntelligenceReports on disk in JSON format and facilitates
reloading and browsing past searches in the Streamlit console.
"""

import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from schemas.models import IntelligenceReport

logger = logging.getLogger(__name__)

SAVED_REPORTS_DIR = Path("saved_reports")


def _ensure_reports_dir() -> Path:
    """Ensures the saved_reports directory exists."""
    SAVED_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return SAVED_REPORTS_DIR


def _slugify(text: str) -> str:
    """Creates a filesystem-safe slug from a topic string."""
    clean = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)[:40] or "report"


def save_report(report: IntelligenceReport) -> str:
    """
    Saves an IntelligenceReport to the saved_reports directory as a JSON file.

    Returns:
        The generated report_id (filename stem).
    """
    reports_dir = _ensure_reports_dir()
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(report.query_topic)
    filename = f"{now_str}_{slug}.json"
    file_path = reports_dir / filename

    try:
        json_data = report.model_dump_json(indent=2)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json_data)
        logger.info(f"Successfully saved report to {file_path}")
        return file_path.stem
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return ""


def list_saved_reports() -> List[Dict[str, Any]]:
    """
    Scans saved_reports/ and returns a list of metadata for all saved searches,
    sorted by newest first.
    """
    reports_dir = _ensure_reports_dir()
    saved = []

    for file_path in reports_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            created_time = datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
            created_str = created_time.strftime("%b %d, %Y %H:%M")

            saved.append({
                "id": file_path.stem,
                "file_path": str(file_path),
                "timestamp_str": created_str,
                "timestamp_epoch": file_path.stat().st_mtime,
                "topic": data.get("query_topic", file_path.stem),
                "jurisdiction": data.get("jurisdiction", "India"),
                "duration_seconds": data.get("execution_time_seconds", 0.0),
                "num_inquiries": len(data.get("inquiries", [])),
                "safety_status": data.get("safety_result", {}).get("status", "NO_SUPPRESSION"),
            })
        except Exception as e:
            logger.warning(f"Could not parse saved report {file_path}: {e}")

    # Sort descending by creation timestamp
    saved.sort(key=lambda x: x["timestamp_epoch"], reverse=True)
    return saved


def load_saved_report(report_id: str) -> Optional[IntelligenceReport]:
    """
    Loads and parses an IntelligenceReport from saved_reports/ by ID or filename.
    """
    reports_dir = _ensure_reports_dir()
    
    # Try exact match or with .json suffix
    if not report_id.endswith(".json"):
        file_path = reports_dir / f"{report_id}.json"
    else:
        file_path = reports_dir / report_id

    if not file_path.exists():
        logger.error(f"Report file not found: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return IntelligenceReport.model_validate_json(content)
    except Exception as e:
        logger.error(f"Failed to load saved report from {file_path}: {e}")
        return None


def delete_saved_report(report_id: str) -> bool:
    """
    Deletes a saved report file from saved_reports/.
    """
    reports_dir = _ensure_reports_dir()
    if not report_id.endswith(".json"):
        file_path = reports_dir / f"{report_id}.json"
    else:
        file_path = reports_dir / report_id

    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"Deleted report {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete report {file_path}: {e}")
            return False
    return False
