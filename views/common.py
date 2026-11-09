"""Small display helpers shared by several pages."""

from datetime import datetime, timezone

import streamlit as st

from weather_app.glossary import GLOSSARY


def show_glossary(terms: list[str] | None = None) -> None:
    """Collapsed 'Glossary' section. Pass a list of terms to show only those."""
    with st.expander("📖 Glossary: aviation terms on this page"):
        for term in terms or GLOSSARY:
            st.markdown(f"**{term}**: {GLOSSARY[term]}")


def scenario_banner(text: str) -> None:
    """Mark anything simulated or hypothetical, so it is never confused with real data."""
    st.warning(f"🧪 **SCENARIO**: {text}")


def age_text(moment: datetime) -> str:
    """'12:30 UTC (25 min ago)' for a timezone-aware UTC datetime."""
    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    ago = f"{minutes} min ago" if minutes < 120 else f"{minutes // 60} h ago"
    return f"{moment:%d %b %H:%M} UTC ({ago})"
