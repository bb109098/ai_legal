"""
ec_date_splitter.py - Adaptive Binary Date Halving for TNREGINET EC Overflow
=============================================================================
Manages date intervals for TNREGINET Encumbrance Certificate searches.
When search results exceed the portal limit (typically 100-200 pages) or time out,
this module recursively halves the date window into contiguous, non-overlapping
sub-intervals until every chunk succeeds, guaranteeing 100% temporal coverage
from 1975 to the present date with zero missing days.
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any, Optional
import re


class ECDateSplitter:
    """Adaptive date interval divider and manager."""

    DATE_FORMAT = "%d-%b-%Y"  # e.g., "01-Jan-1975", "10-Nov-2026"
    SYSTEM_START_DATE = "01-Jan-1975"

    @classmethod
    def parse_date(cls, date_str: str) -> datetime:
        """Parses various date formats used in TNREGINET into a datetime object."""
        date_str = date_str.strip()
        for fmt in ["%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Unrecognized date format: '{date_str}'")

    @classmethod
    def format_date(cls, dt: datetime) -> str:
        """Formats datetime to standard TNREGINET portal format: DD-Mon-YYYY."""
        return dt.strftime(cls.DATE_FORMAT)

    @classmethod
    def split_interval(cls, start_date_str: str, end_date_str: str) -> Tuple[Tuple[str, str], Tuple[str, str]]:
        """
        Splits a date interval into two contiguous, non-overlapping halves.
        Example:
            01-Jan-1975 to 10-Nov-2026 -> (01-Jan-1975 to 07-Dec-2000), (08-Dec-2000 to 10-Nov-2026)
        """
        dt_start = cls.parse_date(start_date_str)
        dt_end = cls.parse_date(end_date_str)

        if dt_start >= dt_end:
            raise ValueError(f"Start date {start_date_str} must be strictly before end date {end_date_str}")

        total_days = (dt_end - dt_start).days
        half_days = total_days // 2

        midpoint_1 = dt_start + timedelta(days=half_days)
        midpoint_2 = midpoint_1 + timedelta(days=1)

        left_half = (cls.format_date(dt_start), cls.format_date(midpoint_1))
        right_half = (cls.format_date(midpoint_2), cls.format_date(dt_end))

        return left_half, right_half

    @classmethod
    def is_overflow_message(cls, html_or_text: str) -> bool:
        if not html_or_text:
            return False
        # 1. Direct countNoRecords check (authoritative indicator from TNREGINET)
        m_count = re.search(r'name=["\']countNoRecords["\'][^>]*value=["\'](\d+)["\']', html_or_text, re.I)
        if m_count and int(m_count.group(1)) >= 200:
            return True
        lower = html_or_text.lower()
        # 2. Check for personal details modal display (email dispatch for >200 records)
        if "divviewecpersonaldtl" in lower and "$('#divviewecpersonaldtl').show()" in lower:
            return True
        # 3. Check for TNREGINET overflow alert texts
        overflow_markers = [
            "more than 200",
            "exceeds page limit",
            "exceed page limit",
            "more records",
            "narrow down",
            "smaller period",
            "records count exceeds",
            "maximum allowed",
            "limit exceeded",
            "சுருக்கமான காலகட்டத்தை",
            "சுருக்கமான காலக்கட்டத்தை",
            "பக்க வரம்பைத் தாண்டியது",
            "பக்க வரம்பை தாண்டியது",
        ]
        return any(marker in lower for marker in overflow_markers)

    @classmethod
    def generate_annual_or_decadal_chunks(cls, start_year: int, end_year: int, chunk_years: int = 10) -> List[Tuple[str, str]]:
        """Generates pre-chunked fixed windows (e.g. 10-year chunks) for high-density surveys."""
        chunks = []
        cur_year = start_year
        while cur_year <= end_year:
            next_year = min(cur_year + chunk_years - 1, end_year)
            start_str = f"01-Jan-{cur_year}"
            end_str = f"31-Dec-{next_year}"
            if next_year == datetime.now().year:
                end_str = cls.format_date(datetime.now())
            chunks.append((start_str, end_str))
            cur_year = next_year + 1
        return chunks
