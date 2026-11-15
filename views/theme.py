"""Look and feel shared by every page: app name, colour palette, page header, cards, badges, charts.

Change APP_NAME here to rename the app everywhere. Colours were checked for contrast on both
background colours (#0B1F3A page, #12294A cards): every chart and status colour reaches at
least 3:1 (the WCAG minimum for graphics), and text colours at least 5:1.

Colour rules
- Chart series use SERIES in this fixed order, never cycled; one place keeps the same colour in
  every chart (ENTITY_COLOURS). More than 8 series: group the rest as "Other".
- Flight category and suitability colours always come with an icon and a text label.
- Magnitude uses one blue ramp (BLUE_RAMP); headwind/tailwind uses blue (tail) → grey → red (head).
- Amber (ACCENT) is for the interface only (buttons, links), never a chart series.
"""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

APP_NAME = "SkyBrief Academy"
TAGLINE = "Aviation weather training for flight schools"
NOTICE = "Training aid only: not for real flight planning."

# ---------------------------------------------------------------- palette ----
BACKGROUND = "#0B1F3A"
SURFACE = "#12294A"
BORDER = "#24406A"
TEXT = "#E8EEF7"
MUTED = "#9FB0C8"       # secondary text (7.5:1 on the background)
AXIS = "#8A9BB5"        # axis lines and tick labels
GRID = "rgba(255,255,255,0.08)"
ACCENT = "#F5A623"      # UI only
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
OTHER = "#898781"
# A city and its airport share one colour, so "Madrid" and "LEMD" look the same in every chart.
_PLACES = [("LEMD", "Madrid"), ("EGLL", "London"), ("LFPG", "Paris"), ("LEBL", "Barcelona"),
           ("LEPA", "Palma"), ("EDDF", "Frankfurt"), ("LIRF", "Rome"), ("EHAM", "Amsterdam")]
ENTITY_COLOURS = {name.casefold(): SERIES[i] for i, pair in enumerate(_PLACES) for name in pair}

BLUE_RAMP = ["#0f2c52", "#164985", "#2067b8", "#3987e5", "#86b6f0", "#b0cff6"]
HEADWIND_SCALE = [[0.0, "#3987e5"], [0.5, OTHER], [1.0, "#e66767"]]  # tail (−) blue, head (+) red
HEAD_COLOUR, TAIL_COLOUR = "#e66767", "#3987e5"

CATEGORY_STYLE = {
    "VFR": {"colour": "#0ca30c", "icon": "☀️", "label": "VFR · good"},
    "MVFR": {"colour": "#3987e5", "icon": "🌤️", "label": "MVFR · moderate"},
    "IFR": {"colour": "#e66767", "icon": "☁️", "label": "IFR · poor"},
    "LIFR": {"colour": "#a94fd0", "icon": "🌫️", "label": "LIFR · very poor"},
}
SUITABILITY_STYLE = {
    "Usable": {"colour": "#0ca30c", "icon": "✅", "label": "Usable"},
    "Caution": {"colour": "#fab219", "icon": "⚠️", "label": "Caution"},
    "Not usable": {"colour": "#d03b3b", "icon": "⛔", "label": "Not usable"},
    "Unknown": {"colour": OTHER, "icon": "❔", "label": "Unknown"},
}
VERDICT_STYLE = {
    "GO": {"colour": "#0ca30c", "icon": "✅", "label": "GO"},
    "CAUTION": {"colour": "#fab219", "icon": "⚠️", "label": "CAUTION"},
    "NO-GO": {"colour": "#d03b3b", "icon": "⛔", "label": "NO-GO"},
}
_UNKNOWN_STYLE = {"colour": OTHER, "icon": "❔", "label": "Unknown"}


def colour_for(name: str) -> str | None:
    """Fixed colour for a known place ('LEMD', 'Madrid, ES', 'london'), else None."""
    key = str(name).split(",")[0].strip().casefold()
    return ENTITY_COLOURS.get(key)


def colour_map(names) -> dict[str, str]:
    """Colour for every series name: known places keep their own colour, the others take
    the next unused SERIES colour in order; anything past eight is grey ("Other")."""
    result, used = {}, set()
    unique = list(dict.fromkeys(str(n) for n in names))
    for name in unique:
        if (colour := colour_for(name)) and colour not in used:
            result[name] = colour
            used.add(colour)
    spare = [c for c in SERIES if c not in used]
    for name in unique:
        if name not in result:
            result[name] = spare.pop(0) if spare else OTHER
    return result


def category_style(category: str | None) -> dict:
    return CATEGORY_STYLE.get(str(category).upper(), _UNKNOWN_STYLE)


def rgb(colour: str, alpha: int = 230) -> list[int]:
    """'#3987e5' → [57, 135, 229, alpha] for pydeck maps."""
    value = colour.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)] + [alpha]


# ---------------------------------------------------------------- page furniture ----
_CSS = f"""
<style>
.block-container {{ padding-top: 4.2rem; padding-bottom: 3rem; max-width: 1280px; }}
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {{ border-color: {BORDER}; }}
[data-testid="stSidebarNav"] span {{ font-size: 0.95rem; }}
/* Amber buttons need dark text: white on amber is only 2:1. */
[data-testid="stBaseButton-primary"]:not(:disabled), [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled) {{
  color: {BACKGROUND} !important; font-weight: 650; border: none; }}
[data-testid="stBaseButton-primary"]:not(:disabled) p,
[data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled) p {{ color: {BACKGROUND} !important; }}
[data-testid="stBaseButton-primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled p {{
  color: {MUTED} !important; }}
[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 0.6rem;
  padding: 0.75rem 1rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; }}
[data-testid="stCode"] pre, .stCode pre {{ font-size: 1.02rem; }}
.sb-hero {{ background: linear-gradient(135deg, {SURFACE} 0%, {BACKGROUND} 100%); border: 1px solid {BORDER};
  border-radius: 0.9rem; padding: 1.3rem 1.5rem 1.1rem; margin-bottom: 1.2rem; }}
.sb-kicker {{ color: {ACCENT}; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }}
.sb-hero h1 {{ font-size: 1.9rem; line-height: 1.2; margin: 0.25rem 0 0.35rem; padding: 0; color: {TEXT}; }}
.sb-hero p {{ color: {MUTED}; margin: 0; font-size: 1.02rem; }}
.sb-notice {{ margin-top: 0.7rem !important; font-size: 0.82rem !important; color: {MUTED}; }}
.sb-card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 0.7rem; padding: 0.9rem 1rem;
  height: 100%; }}
.sb-card h4 {{ margin: 0 0 0.3rem; padding: 0; font-size: 1.02rem; color: {TEXT}; }}
.sb-card p {{ margin: 0; color: {MUTED}; font-size: 0.93rem; }}
.sb-badge {{ display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; border: 1px solid;
  font-weight: 650; font-size: 0.9rem; color: {TEXT}; white-space: nowrap; }}
.sb-raw {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #081830;
  border: 1px solid {BORDER}; border-left: 4px solid {ACCENT}; border-radius: 0.5rem; padding: 0.8rem 1rem;
  font-size: 1.05rem; color: {TEXT}; overflow-wrap: anywhere; }}
</style>
"""


def apply_theme() -> None:
    """Page-wide CSS on top of .streamlit/config.toml. Call once per run (app.py does)."""
    st.html(_CSS)


def hero(title: str, subtitle: str, kicker: str = APP_NAME) -> None:
    """The header block at the top of every page, with the training notice."""
    st.markdown(
        f'<div class="sb-hero"><div class="sb-kicker">{html.escape(kicker)}</div>'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
        f'<p class="sb-notice">⚠️ {html.escape(NOTICE)}</p></div>',
        unsafe_allow_html=True,
    )


def card(title: str, body: str, icon: str = "", accent: str | None = None) -> None:
    """A small information card. `accent` draws a coloured left edge (e.g. a status colour)."""
    edge = f' style="border-left: 4px solid {accent};"' if accent else ""
    st.markdown(
        f'<div class="sb-card"{edge}><h4>{html.escape(f"{icon} {title}".strip())}</h4>'
        f"<p>{html.escape(body)}</p></div>",
        unsafe_allow_html=True,
    )


def status_badge(kind: str, text: str | None = None) -> str:
    """HTML pill for a flight category, suitability status or verdict: icon + label + colour."""
    style = (CATEGORY_STYLE.get(kind) or SUITABILITY_STYLE.get(kind) or VERDICT_STYLE.get(kind)
             or _UNKNOWN_STYLE)
    label = html.escape(text or style["label"])
    colour = style["colour"]
    return (f'<span class="sb-badge" style="border-color:{colour}; background:{colour}33;">'
            f"{style['icon']} {label}</span>")


def badge(kind: str, text: str | None = None) -> None:
    st.markdown(status_badge(kind, text), unsafe_allow_html=True)


def raw_report(text: str) -> None:
    """A raw METAR/TAF in monospace, highlighted as 'the coded text'."""
    st.markdown(f'<div class="sb-raw">{html.escape(text)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- charts ----
def style_figure(fig: go.Figure, height: int | None = None) -> go.Figure:
    """Apply the house chart style: transparent background, light text, hairline grid, one y-axis,
    2 px lines, 8 px markers, gaps between stacked bars, legend only for 2+ series."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT, "color": TEXT, "size": 13},
        title={"font": {"size": 16, "color": TEXT}, "x": 0, "xanchor": "left"},
        hoverlabel={"bgcolor": SURFACE, "bordercolor": BORDER, "font": {"color": TEXT, "family": FONT}},
        legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": TEXT}, "orientation": "h",
                "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0, "title": {"text": ""}},
        margin={"t": 80, "b": 60, "l": 70, "r": 20},
    )
    axis = {"gridcolor": GRID, "linecolor": AXIS, "zerolinecolor": "rgba(255,255,255,0.25)", "automargin": True,
            "tickfont": {"color": AXIS}, "title": {"font": {"color": MUTED}, "standoff": 12}}
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    if height:
        fig.update_layout(height=height)

    for trace in fig.data:
        if trace.type == "scatter":
            mode = trace.mode or "lines"
            if "lines" in mode:
                trace.line.width = 2
            size = trace.marker.size
            if "markers" in mode and (size is None or (isinstance(size, (int, float)) and size < 8)):
                trace.marker.size = 8
    if fig.layout.barmode == "stack":
        fig.update_traces(marker_line={"width": 2, "color": BACKGROUND}, selector={"type": "bar"})
    shown = [t for t in fig.data if t.showlegend is not False and t.type not in ("heatmap",)]
    fig.update_layout(showlegend=len(shown) >= 2)
    return fig


def figure_table(fig: go.Figure) -> pd.DataFrame:
    """The numbers behind a line, scatter or bar chart as a table (columns named after the axes)."""
    x_title = fig.layout.xaxis.title.text or "x"
    y_title = fig.layout.yaxis.title.text or "y"
    frames = []
    for trace in fig.data:
        if trace.type not in ("scatter", "bar") or trace.x is None or trace.y is None:
            continue
        frame = pd.DataFrame({x_title: list(trace.x), y_title: list(trace.y)})
        if len(fig.data) > 1:
            frame.insert(0, "Series", trace.name or "")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def chart(fig: go.Figure, data: pd.DataFrame | None = None, height: int | None = None, key: str | None = None) -> None:
    """Draw a styled Plotly chart, with its numbers in a 'Show data' expander underneath.

    Without `data`, the table is read from the chart itself (figure_table)."""
    st.plotly_chart(style_figure(fig, height), width="stretch", theme=None, key=key)
    table = figure_table(fig) if data is None else data
    if not table.empty:
        with st.expander("Show data"):
            st.dataframe(table, hide_index=True, width="stretch")


def empty_state(message: str, icon: str = "🛰️") -> None:
    """What a chart area shows when there is nothing to draw yet."""
    st.info(f"{icon} {message}")
