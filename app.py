"""Peer Comparison Studio: interactive app.

    py -m streamlit run app.py

Reads the tables built by `py -m studio.build`. Nothing here changes the data;
every number shown comes from data/processed/observations.csv.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from studio import metrics as metmod
from studio import peers as peermod
from studio.compare import compare, trend
from studio.paths import PROCESSED_DIR

# Read at run time so tests (and other setups) can point the app at another build.
DATA_DIR = Path(os.environ.get("PCS_PROCESSED_DIR", PROCESSED_DIR))

st.set_page_config(page_title="Peer Comparison Studio", page_icon="📊", layout="wide")

BENCH_COLOR = "#1f4e79"
PEER_COLOR = "#a9b8c9"
MEDIAN_COLOR = "#c0504d"

CATEGORY = {"EFA": "Enrollment", "EFIA": "Enrollment", "EFD": "Retention", "GR": "Graduation",
            "HR": "Faculty", "F": "Finance", "derived": "Finance (per student)"}
CATEGORY_ORDER = ["Enrollment", "Retention", "Graduation", "Faculty", "Finance", "Finance (per student)"]

# Metrics shown on the Scorecard tab, in order.
SCORECARD = [
    "enr_total", "fte_12month", "enr_ft_first_time", "ret_ft_rate", "student_faculty_ratio",
    "grad_rate_150", "bach_grad_rate_4yr", "bach_grad_rate_6yr", "transfer_out_rate",
    "fac_ft_instructional", "fac_pct_tenured", "rev_tuition_share", "rev_investment_share",
    "rev_private_gifts_share", "discount_rate_estimate", "exp_instruction_per_fte",
    "exp_student_services_per_fte", "exp_institutional_support_per_fte", "rev_tuition_per_fte",
    "endowment_per_fte",
]


# --------------------------------------------------------------------------- data

@st.cache_data
def load_tables(data_dir: str):
    data_dir = Path(data_dir)
    obs = pd.read_csv(data_dir / "observations.csv", dtype={"unitid": str, "flag": str})
    members = pd.read_csv(data_dir / "peer_groups.csv", dtype={"UNITID": str})
    inst = pd.read_csv(data_dir / "institutions.csv", dtype={"UNITID": str})
    obs["flag"] = obs["flag"].fillna("")
    return obs, members, dict(zip(inst["UNITID"], inst["INSTNM"]))


def fmt(value, unit: str) -> str:
    if value is None or pd.isna(value):
        return "–"
    if unit == "percent":
        return f"{value:.1f}%"
    if unit.startswith("dollars"):
        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:,.1f}M"
        return f"${value:,.0f}"
    if unit.startswith("ratio"):
        return f"{value:.0f} to 1"
    return f"{value:,.0f}"


def gap_text(bench, median, unit: str) -> str:
    if bench is None or median is None or pd.isna(bench) or pd.isna(median):
        return ""
    diff = bench - median
    if unit == "percent":
        return f"{diff:+.1f} pts vs. median"
    if median:
        return f"{diff / median * 100:+.0f}% vs. median"
    return ""


if not (DATA_DIR / "observations.csv").exists():
    st.error("No data yet. In the terminal run:  py -m studio.build --years 2015-2024")
    st.stop()

obs, members, names = load_tables(str(DATA_DIR))
catalog = metmod.catalog()
groups = peermod.load_all()
available = set(obs["metric"].unique())

# --------------------------------------------------------------------------- sidebar

st.sidebar.title("Peer Comparison Studio")

group_id = st.sidebar.selectbox("Peer group", list(groups), format_func=lambda g: groups[g].label)
group = groups[group_id]
bench = group.benchmark
bench_name = names.get(bench, bench)
group_members = members[members["group_id"] == group_id]
st.sidebar.caption(f"{group.name}: {bench_name} vs. {len(group_members)} institutions")

cats = [c for c in CATEGORY_ORDER
        if any(CATEGORY[m.survey] == c and m.id in available for m in catalog.values())]
category = st.sidebar.radio("Topic", cats)
options = [m.id for m in catalog.values() if CATEGORY[m.survey] == category and m.id in available]
metric_id = st.sidebar.selectbox("Measure", options, format_func=lambda m: catalog[m].label)
metric = catalog[metric_id]

subgroups = sorted(obs.loc[obs["metric"] == metric_id, "subgroup"].unique(),
                   key=lambda s: (s != "total", s not in ("men", "women"), s))
subgroup = "total"
if len(subgroups) > 1:
    subgroup = st.sidebar.selectbox("Student or staff group", subgroups,
                                    format_func=lambda s: s.replace("_", " ").capitalize())

years = sorted(obs.loc[obs["metric"] == metric_id, "year"].unique(), reverse=True)
year = st.sidebar.selectbox("Year", years)

st.sidebar.divider()
st.sidebar.caption("Source: U.S. Department of Education, NCES, IPEDS. Not affiliated with or endorsed by NCES.")

# --------------------------------------------------------------------------- header

who = "" if subgroup == "total" else f" · {subgroup.replace('_', ' ')}"
st.title(f"{metric.label}{who}")
period = obs.loc[(obs["metric"] == metric_id) & (obs["year"] == year), "period"]
st.caption(f"{period.iloc[0] if len(period) else year} · {group.name}")

tab_compare, tab_trend, tab_score, tab_group, tab_about = st.tabs(
    ["Compare", "Trend", "Scorecard", "Peer group", "Definitions & sources"])

# --------------------------------------------------------------------------- compare

with tab_compare:
    table, summary = compare(obs, members, names, group_id, bench, metric_id, int(year), subgroup)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(bench_name, fmt(summary["benchmark_value"], metric.unit))
    c2.metric("Peer median", fmt(summary["peer_median"], metric.unit),
              gap_text(summary["benchmark_value"], summary["peer_median"], metric.unit) or None,
              delta_color="off")
    c3.metric("Peer range", f"{fmt(summary['peer_min'], metric.unit)} – {fmt(summary['peer_max'], metric.unit)}")
    c4.metric("Rank (highest = 1)", summary["benchmark_rank"] or "–")

    plot = table.dropna(subset=["value"]).sort_values("value")
    if len(plot):
        colors = [BENCH_COLOR if r == "benchmark" else PEER_COLOR for r in plot["role"]]
        fig = go.Figure(go.Bar(
            x=plot["value"], y=plot["institution"], orientation="h", marker_color=colors,
            text=[fmt(v, metric.unit) for v in plot["value"]], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{text}<extra></extra>"))
        if summary["peer_median"] is not None:
            fig.add_vline(x=summary["peer_median"], line_dash="dash", line_color=MEDIAN_COLOR,
                          annotation_text="Peer median", annotation_position="top")
        fig.update_layout(height=max(320, 26 * len(plot) + 80), margin=dict(l=10, r=60, t=30, b=10),
                          xaxis_title=metric.unit, yaxis_title=None, showlegend=False)
        st.plotly_chart(fig, width="stretch")
    missing = table[table["value"].isna()]["institution"].tolist()
    if missing:
        st.caption(f"No value reported: {', '.join(missing)}")

    with st.expander("Table"):
        st.dataframe(table, hide_index=True, width="stretch")
    st.download_button("Download this comparison (CSV)", table.to_csv(index=False).encode(),
                       file_name=f"{metric_id}_{subgroup}_{year}_{group_id}.csv", mime="text/csv")

# --------------------------------------------------------------------------- trend

with tab_trend:
    t = trend(obs, members, group_id, bench, metric_id, subgroup)
    if t.empty:
        st.info("No data for this measure.")
    else:
        ids = set(group_members["UNITID"])
        rng = (obs[(obs["metric"] == metric_id) & (obs["subgroup"] == subgroup) & obs["unitid"].isin(ids)]
               .groupby("year")["value"].agg(["min", "max"]).reset_index())
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=rng["year"], y=rng["max"], line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=rng["year"], y=rng["min"], line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(169,184,201,0.35)", name="Peer range", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=t["year"], y=t["peer_median"], name="Peer median",
                                 line=dict(color=MEDIAN_COLOR, dash="dash"), mode="lines+markers"))
        fig.add_trace(go.Scatter(x=t["year"], y=t["benchmark"], name=bench_name,
                                 line=dict(color=BENCH_COLOR, width=3), mode="lines+markers"))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=metric.unit,
                          xaxis=dict(dtick=1), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")
        st.caption("Peer group members are fixed to the directory year used in the build, "
                   "so the same institutions are compared every year.")
        st.dataframe(t, hide_index=True, width="stretch")
        st.download_button("Download trend (CSV)", t.to_csv(index=False).encode(),
                           file_name=f"{metric_id}_{subgroup}_trend_{group_id}.csv", mime="text/csv")

# --------------------------------------------------------------------------- scorecard

with tab_score:
    st.subheader(f"{bench_name} at a glance")
    rows = []
    for mid in SCORECARD:
        if mid not in available:
            continue
        m = catalog[mid]
        yrs = obs.loc[obs["metric"] == mid, "year"]
        y = int(year) if int(year) in set(yrs) else int(yrs.max())
        _, s = compare(obs, members, names, group_id, bench, mid, y, "total")
        rows.append({"Topic": CATEGORY[m.survey], "Measure": m.label, "Period": s["period"],
                     bench_name: fmt(s["benchmark_value"], m.unit),
                     "Peer median": fmt(s["peer_median"], m.unit),
                     "Gap": gap_text(s["benchmark_value"], s["peer_median"], m.unit),
                     "Rank": s["benchmark_rank"] or "–", "Peers with data": s["peer_n"]})
    score = pd.DataFrame(rows)
    st.dataframe(score, hide_index=True, width="stretch", height=36 * (len(score) + 1))
    st.caption("Rank 1 is the highest value, whether or not higher is better for that measure.")
    st.download_button("Download scorecard (CSV)", score.to_csv(index=False).encode(),
                       file_name=f"scorecard_{year}_{group_id}.csv", mime="text/csv")

# --------------------------------------------------------------------------- peer group

with tab_group:
    st.subheader(group.name)
    if group.description:
        st.write(group.description)
    st.caption(f"Type: {group.type} · Benchmark: {bench_name} ({bench})"
               + (f" · Source: {group.source}" if group.source else ""))
    if group.rules:
        st.write("Rules:", group.rules)
    st.dataframe(group_members[["INSTNM", "CITY", "STABBR", "UNITID", "reason"]].rename(
        columns={"INSTNM": "Institution", "CITY": "City", "STABBR": "State", "reason": "Why included"}),
        hide_index=True, width="stretch")
    st.caption("Add or change groups in config/peer_groups/, then rebuild.")

# --------------------------------------------------------------------------- definitions

with tab_about:
    st.subheader(metric.label)
    st.write(metric.definition)
    src = obs.loc[(obs["metric"] == metric_id) & (obs["year"] == year) & (obs["unitid"] == bench)]
    st.markdown(f"- **Unit:** {metric.unit}\n- **Survey:** {metric.survey}\n"
                f"- **Source file:** {src['source_file'].iloc[0] if len(src) else '–'}\n"
                f"- **Source variable:** {src['source_variable'].iloc[0] if len(src) else '–'}")
    st.markdown("**Status flags**")
    st.dataframe(pd.DataFrame(metmod.FLAG_MEANINGS.items(), columns=["Flag", "Meaning"]),
                 hide_index=True)
