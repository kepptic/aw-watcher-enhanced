"""
Daily summary generation for aw-watcher-enhanced.

Aggregates events by app and category, computes time spent,
context switches, meeting time, and first/last active times.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from aw_client import ActivityWatchClient

from .config import load_config

logger = logging.getLogger(__name__)

WATCHER_NAME = "aw-watcher-enhanced"


class DailySummary:
    """Generates daily activity summaries from event data."""

    def __init__(self, testing: bool = False):
        self.testing = testing
        self.config = load_config()
        # Use a different client name for CLI tools to avoid single-instance lock
        self.client = ActivityWatchClient(f"{WATCHER_NAME}-cli", testing=testing)
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"

    def generate(self, date: datetime) -> Dict[str, Any]:
        """Generate a summary for the given date.

        Args:
            date: The date to summarize (time part is ignored).

        Returns:
            Dict with summary data.
        """
        start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        with self.client:
            events = self.client.get_events(
                self.bucket_id,
                start=start,
                end=end,
                limit=-1,
            )

        if not events:
            return {"date": start.strftime("%Y-%m-%d"), "total_events": 0}

        # Aggregate data
        time_by_app: Dict[str, float] = defaultdict(float)
        time_by_category: Dict[str, float] = defaultdict(float)
        meeting_time: float = 0.0
        context_switches = 0
        last_app = None
        first_active = None
        last_active = None

        for event in events:
            duration = event.duration.total_seconds()
            app = event.data.get("app", "unknown")
            category = event.data.get("category", "Uncategorized")

            time_by_app[app] += duration
            time_by_category[category] += duration

            if event.data.get("in_meeting"):
                meeting_time += duration

            if app != last_app:
                if last_app is not None:
                    context_switches += 1
                last_app = app

            ts = event.timestamp
            if first_active is None:
                first_active = ts
            last_active = ts

        total_tracked = sum(time_by_app.values())

        return {
            "date": start.strftime("%Y-%m-%d"),
            "total_events": len(events),
            "total_tracked_seconds": round(total_tracked, 1),
            "total_tracked_formatted": _format_duration(total_tracked),
            "first_active": first_active.isoformat() if first_active else None,
            "last_active": last_active.isoformat() if last_active else None,
            "context_switches": context_switches,
            "meeting_time_seconds": round(meeting_time, 1),
            "meeting_time_formatted": _format_duration(meeting_time),
            "time_by_app": {
                k: {"seconds": round(v, 1), "formatted": _format_duration(v)}
                for k, v in sorted(time_by_app.items(), key=lambda x: -x[1])
            },
            "time_by_category": {
                k: {"seconds": round(v, 1), "formatted": _format_duration(v)}
                for k, v in sorted(time_by_category.items(), key=lambda x: -x[1])
            },
        }


def _format_duration(seconds: float) -> str:
    """Format seconds as h:mm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}:{minutes:02d}"


def run_summary(
    date_str: str = "today",
    output_format: str = "text",
    testing: bool = False,
):
    """CLI entry point for daily summary.

    Args:
        date_str: Date string — "today", "yesterday", or "YYYY-MM-DD".
        output_format: "text" or "json".
        testing: Use testing server.
    """
    if date_str == "today":
        date = datetime.now(timezone.utc)
    elif date_str == "yesterday":
        date = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        date = datetime.strptime(date_str, "%Y-%m-%d")

    summary_gen = DailySummary(testing=testing)
    summary = summary_gen.generate(date)

    if output_format == "json":
        print(json.dumps(summary, indent=2))
        return

    # Text format
    print(f"\n{'=' * 60}")
    print(f"  Daily Summary — {summary['date']}")
    print(f"{'=' * 60}")

    if summary["total_events"] == 0:
        print("\n  No events recorded for this date.\n")
        return

    print(f"\n  Total tracked:     {summary['total_tracked_formatted']}")
    if summary.get("first_active"):
        first = summary["first_active"][:19].replace("T", " ")
        last = summary["last_active"][:19].replace("T", " ")
        print(f"  First active:      {first}")
        print(f"  Last active:       {last}")
    print(f"  Context switches:  {summary['context_switches']}")
    print(f"  Meeting time:      {summary['meeting_time_formatted']}")
    print(f"  Total events:      {summary['total_events']}")

    # Apps table
    print(f"\n  {'App':<30} {'Time':>8}")
    print(f"  {'-' * 30} {'-' * 8}")
    for app, data in summary["time_by_app"].items():
        print(f"  {app[:29]:<30} {data['formatted']:>8}")

    # Categories table
    print(f"\n  {'Category':<40} {'Time':>8}")
    print(f"  {'-' * 40} {'-' * 8}")
    for cat, data in summary["time_by_category"].items():
        print(f"  {cat[:39]:<40} {data['formatted']:>8}")

    print()
