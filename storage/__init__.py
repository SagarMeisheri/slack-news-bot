"""
Storage package for saving, managing, and retrieving past intelligence investigation reports.
"""

from .history import (
    SAVED_REPORTS_DIR,
    delete_saved_report,
    list_saved_reports,
    load_saved_report,
    save_report,
)

__all__ = [
    "SAVED_REPORTS_DIR",
    "save_report",
    "list_saved_reports",
    "load_saved_report",
    "delete_saved_report",
]
