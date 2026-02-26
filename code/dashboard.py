"""
dashboard.py
============
Streamlit dashboard — HYROX Doubles Open Males global results evolution.

Run:
    streamlit run dashboard.py

Expects hyrox_results.csv produced by fetch_hyrox.py in the same folder.
"""

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HYROX Doubles Open Males – Global Evolution",
    page_icon="🏋️",
    layout="wide",
)

DATA_FILE = Path(__file__).parent / "hyrox_results.csv"

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def load_data(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath, dtype=str)

    # Convert total_time (HH:MM:SS or MM:SS) → total seconds
    def to_seconds(t):
        if pd.isna(t) or not isinstance(t, str):
            return None
        t = t.strip()
        m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})", t)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m2 = re.fullmatch(r"(\d+):(\d{2})", t)
        if m2:
            return int(m2.group(1)) * 60 + int(m2.group(2))
        return None

    df["total_seconds"] = df["total_time"].apply(to_seconds)
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")

    # Extract year from event_main_group (e.g. "2026 Taipei" → 2026)
    df["year"] = df["event_main_group"].str.extract(r"(20\d{2})")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")

    # Display label: "Season X | City Year" — used as x-axis in charts
    df["display_label"] = df["season"].fillna("") + " | " + df["event_main_group"].fillna("")

    return df.dropna(subset=["total_seconds"])


def fmt_seconds(s: float) -> str:
    """Format total seconds as H:MM:SS."""
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


# ── Load ──────────────────────────────────────────────────────────────────────

if not DATA_FILE.exists():
    st.error(
        f"**Data file not found:** `{DATA_FILE}`\n\n"
        "Run `python fetch_hyrox.py` first to download the results."
    )
    st.stop()

df = load_data(DATA_FILE)

# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Filters")

    seasons = sorted(df["season"].dropna().unique())
    sel_seasons = st.multiselect("Season(s)", seasons, default=seasons)

    nationalities = sorted(df["nationality"].dropna().unique())
    if nationalities:
        sel_nat = st.multiselect("Nationality (optional)", nationalities)
    else:
        sel_nat = []

    max_rank_val = int(df["rank"].max()) if df["rank"].max() > 0 else 100
    min_rank, max_rank = st.slider(
        "Rank range (top N finishers per event)",
        min_value=1, max_value=max_rank_val,
        value=(1, min(100, max_rank_val)),
    )

# ── Apply filters ─────────────────────────────────────────────────────────────

mask = (
    df["season"].isin(sel_seasons) &
    df["rank"].between(min_rank, max_rank)
)
if sel_nat:
    mask &= df["nationality"].isin(sel_nat)

dff = df[mask].copy()

if dff.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("HYROX Doubles Open Males – Global Results Evolution")
st.caption(
    f"Showing **{len(dff):,}** athlete-results across "
    f"**{dff['event_code'].nunique()}** events · "
    f"Top {min_rank}–{max_rank} finishers per event"
)

# ── KPI row ───────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total finishers", f"{len(dff):,}")
col2.metric("Events", f"{dff['event_code'].nunique()}")
col3.metric("World record (top 1)", fmt_seconds(dff["total_seconds"].min()))
col4.metric("Median finish time", fmt_seconds(dff["total_seconds"].median()))

st.divider()

# ── 1. Season comparison tables ──────────────────────────────────────────

st.subheader("Season Comparison – Top finishers side by side")

display_cols = ["event_main_group", "rank", "athlete", "age_group", "total_time"]
display_cols = [c for c in display_cols if c in dff.columns]

available_seasons = sorted(dff["season"].dropna().unique())
if len(available_seasons) >= 2:
    col_left, col_right = st.columns(2)

    with col_left:
        season_a = st.selectbox("Season A", available_seasons, index=0, key="cmp_a")
        df_a = dff[dff["season"] == season_a][display_cols].sort_values(["event_main_group", "rank"])
        st.caption(f"**{season_a}** — {len(df_a):,} results")
        st.dataframe(df_a, use_container_width=True, height=500)

    with col_right:
        season_b = st.selectbox("Season B", available_seasons,
                                index=len(available_seasons) - 1, key="cmp_b")
        df_b = dff[dff["season"] == season_b][display_cols].sort_values(["event_main_group", "rank"])
        st.caption(f"**{season_b}** — {len(df_b):,} results")
        st.dataframe(df_b, use_container_width=True, height=500)
else:
    st.info("Need at least 2 seasons to compare. Only 1 season in the data.")
    df_only = dff[display_cols].sort_values(["event_main_group", "rank"])
    st.dataframe(df_only, use_container_width=True, height=500)

st.divider()

# ── 2. World Record Progression ───────────────────────────────────────────────

st.subheader("Best Time per Event")

wr = (
    dff.groupby(["display_label", "event_main_group", "season", "year"])["total_seconds"]
    .min()
    .reset_index()
    .sort_values(["year", "event_main_group"])
)
wr["best_time_fmt"] = wr["total_seconds"].apply(fmt_seconds)

fig_wr = px.scatter(
    wr,
    x="display_label",
    y="total_seconds",
    color="season",
    hover_name="event_main_group",
    hover_data={"best_time_fmt": True, "total_seconds": False, "season": True},
    labels={"total_seconds": "Best time (s)", "display_label": "Event"},
    title="Winning time per event",
)
fig_wr.update_traces(mode="lines+markers", line=dict(dash="dot"))
fig_wr.update_layout(
    yaxis=dict(
        tickvals=list(range(3000, 9000, 300)),
        ticktext=[fmt_seconds(s) for s in range(3000, 9000, 300)],
    ),
    xaxis_tickangle=-45,
    height=450,
)
st.plotly_chart(fig_wr, use_container_width=True)

# ── 2. Time Distribution per Event ────────────────────────────────────────────

st.subheader("Finish Time Distribution per Event")
st.caption("Box plot showing median, quartiles, and outliers for each event.")

fig_box = px.box(
    dff.sort_values(["year", "event_main_group"]),
    x="display_label",
    y="total_seconds",
    color="season",
    labels={"total_seconds": "Finish time (s)", "display_label": "Event"},
    points=False,
)
fig_box.update_layout(
    yaxis=dict(
        tickvals=list(range(3000, 12000, 600)),
        ticktext=[fmt_seconds(s) for s in range(3000, 12000, 600)],
    ),
    xaxis_tickangle=-45,
    height=500,
)
st.plotly_chart(fig_box, use_container_width=True)

# ── 3. Average time trend over seasons ───────────────────────────────────────

st.subheader("Average Finish Time – Season Trend")

season_avg = (
    dff.groupby("season")["total_seconds"]
    .agg(["mean", "median", "min", "count"])
    .reset_index()
    .rename(columns={"mean": "avg", "count": "finishers"})
)
season_avg["avg_fmt"] = season_avg["avg"].apply(fmt_seconds)
season_avg["median_fmt"] = season_avg["median"].apply(fmt_seconds)

fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(
    x=season_avg["season"], y=season_avg["avg"],
    mode="lines+markers", name="Average",
    hovertemplate="%{x}: %{customdata}",
    customdata=season_avg["avg_fmt"],
))
fig_trend.add_trace(go.Scatter(
    x=season_avg["season"], y=season_avg["median"],
    mode="lines+markers", name="Median",
    hovertemplate="%{x}: %{customdata}",
    customdata=season_avg["median_fmt"],
    line=dict(dash="dash"),
))
fig_trend.update_layout(
    yaxis=dict(
        title="Time (H:MM:SS)",
        tickvals=list(range(3600, 9000, 300)),
        ticktext=[fmt_seconds(s) for s in range(3600, 9000, 300)],
    ),
    xaxis_title="Season",
    height=380,
    legend=dict(orientation="h"),
)
st.plotly_chart(fig_trend, use_container_width=True)

# ── 4. Top Countries ──────────────────────────────────────────────────────────
# (Skipped — nationality data not available for Doubles events)


# ── 7. Raw data table ─────────────────────────────────────────────────────────

with st.expander("Full raw data table"):
    all_cols = [
        "season", "event_main_group", "event_label", "category",
        "gender", "rank", "athlete", "age_group", "total_time",
    ]
    all_cols = [c for c in all_cols if c in dff.columns]
    st.dataframe(dff[all_cols].sort_values(["event_main_group", "rank"]), use_container_width=True)
    st.download_button(
        "Download filtered CSV",
        data=dff[all_cols].to_csv(index=False).encode(),
        file_name="hyrox_filtered.csv",
        mime="text/csv",
    )
