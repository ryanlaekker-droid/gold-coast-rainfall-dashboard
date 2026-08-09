"""
Gold Coast Airport rainfall / fieldwork outlook.

Reads data/latest.json and displays it. Makes no network requests and
performs no calculations - collect.py does all of that on a schedule.
"""

import json
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config

st.set_page_config(page_title="Gold Coast Rainfall Outlook",
                   layout="wide", initial_sidebar_state="collapsed")

STATUS_COLOURS = {"green": "#1D9E75", "amber": "#BA7517", "white": "#888780"}
MODEL_COLOURS = {"GFS": "#eb6834", "UKMO": "#1baf7a", "ICON": "#eda100"}
ECMWF_COLOUR = "#2a78d6"
DASHES = {"GFS": "dash", "UKMO": "dot", "ICON": "dashdot"}
GE = "\u2265"
DASH = "\u2013"
ARROW = "\u2192"
DAY_MS = 86400000.0

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1250px;}
  h1 {font-size: 1.6rem !important; margin-bottom: 0 !important;}
  h2 {font-size: 1.1rem !important; margin-top: 1.2rem !important;}
  h3 {font-size: 0.95rem !important;}
  .status-line {font-size: 1.5rem; font-weight: 600; margin: 0.4rem 0 0.2rem;}
  .muted {color: #8a8a86; font-size: 0.85rem; line-height: 1.5;}
  .panel {border: 1px solid rgba(128,128,128,0.25); border-radius: 8px;
          padding: 0.8rem 1rem; margin-bottom: 0.5rem;}
  .panel-label {font-size: 0.78rem; color: #8a8a86; margin-bottom: 0.2rem;}
  .panel-value {font-size: 1.7rem; font-weight: 600; line-height: 1.2;}
  .panel-sub {font-size: 0.82rem; color: #8a8a86; margin-top: 0.2rem;}
  .band {background: rgba(42,120,214,0.10); border-left: 4px solid #2a78d6;
         padding: 0.45rem 0.8rem; margin: 0.6rem 0; font-size: 0.88rem;}
  .stale {background: rgba(186,117,23,0.15); border-left: 4px solid #BA7517;
          padding: 0.6rem 0.9rem; margin: 0.5rem 0; font-size: 0.9rem;}
  .failed {background: rgba(163,45,45,0.15); border-left: 4px solid #A32D2D;
           padding: 0.6rem 0.9rem; margin: 0.5rem 0; font-size: 0.9rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load():
    if not config.LATEST_FILE.exists():
        return None
    return json.loads(config.LATEST_FILE.read_text(encoding="utf-8"))


def age_hours(iso_timestamp):
    generated = datetime.fromisoformat(iso_timestamp)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - generated).total_seconds() / 3600


def fmt(value):
    return DASH if value is None else f"{value:.1f}"


def panel(label, value, sub):
    return (f"<div class='panel'><div class='panel-label'>{label}</div>"
            f"<div class='panel-value'>{value}</div>"
            f"<div class='panel-sub'>{sub}</div></div>")


def highlight(row, limit, only=None):
    if only is not None and row.name != only:
        return [""] * len(row)
    marks = []
    for value in row:
        try:
            marks.append("background-color: rgba(186,117,23,0.28)"
                         if float(value) >= limit else "")
        except (TypeError, ValueError):
            marks.append("")
    return marks


def bom_visible(rows):
    """Keep steps up to the last one carrying a rainfall amount.

    Beyond that BOM publishes only chance of any rain, so the amount
    columns would be entirely blank.
    """
    amounts = [position for position, row in enumerate(rows)
               if any(row.get(key) is not None
                      for key in ("mm_50pct", "mm_25pct", "mm_10pct"))]
    last = max(amounts) + 1 if amounts else len(rows)
    return rows[:min(last, config.BOM_MAX_STEPS)]


data = load()

if data is None:
    st.title("Gold Coast Airport")
    st.error("No data file found. Run `python collect.py` first.")
    st.stop()

threshold = data["threshold_mm"]
age = age_hours(data["generated_at_utc"])
now_local = pd.Timestamp.now(tz=config.LOCAL_TZ)
model_labels = [m["label"] for m in config.DETERMINISTIC_MODELS]
rain_day = data.get("window_mode", "rain_day") == "rain_day"

# --- Header -------------------------------------------------------------

st.title("Gold Coast Airport")
st.markdown("**Rainfall / fieldwork outlook**")

left, right = st.columns([3, 2])
generated = pd.Timestamp(data["generated_at_local"])
left.markdown(f"<span class='muted'>{now_local:%A %d %B %Y, %H:%M} AEST</span>",
              unsafe_allow_html=True)
right.markdown(f"<span class='muted'>Last update: "
               f"{generated:%a %d %b %H:%M} AEST ({age:.1f} h ago)</span>",
               unsafe_allow_html=True)

if age > 12:
    st.markdown(f"<div class='stale'>Data is {age:.0f} hours old. "
                f"The scheduled update may have failed.</div>",
                unsafe_allow_html=True)

# --- Headline -----------------------------------------------------------

head = data["headline"]
colour = STATUS_COLOURS[head["status_code"]]

st.markdown(f"<div class='status-line' style='color:{colour}'>"
            f"{head['status_text']}</div>", unsafe_allow_html=True)

st.markdown("<div class='band'><b>ECMWF ensemble</b> \u2014 51 members. "
            "Every figure in this section, including P10 and P90, comes from "
            "that one ensemble. The window below is the true rolling maximum, "
            "searched across every start hour.</div>", unsafe_allow_html=True)

start = pd.Timestamp(head["window_start_local"])
end = pd.Timestamp(head["window_end_local"])

a, b, c = st.columns(3)
a.markdown(panel("Best 24-hour window",
                 f"{start:%a %d %b %H:%M}",
                 f"{ARROW} {end:%a %d %b %H:%M} AEST"), unsafe_allow_html=True)
b.markdown(panel("ECMWF ensemble mean",
                 f"{head['ecmwf_mean']:.1f} mm",
                 f"P10\u2013P90 {head['ecmwf_p10']:.1f}\u2013"
                 f"{head['ecmwf_p90']:.1f} mm"), unsafe_allow_html=True)
c.markdown(panel(f"ECMWF members {GE}{threshold:.0f} mm",
                 f"{head['members_over']}/{head['members_total']}",
                 f"{head['percent_over']}% of the 51 members"),
           unsafe_allow_html=True)

verdict = data["agreement"]
st.markdown(f"**Model agreement: {verdict['level'].upper()}**")
st.markdown(f"<span class='muted'>{verdict['reasoning']}</span>",
            unsafe_allow_html=True)

st.divider()

# --- Main chart ---------------------------------------------------------

st.markdown("## Rolling 24-hour rainfall")

curve = pd.DataFrame(data["rolling_curve"])
curve["t"] = pd.to_datetime(curve["window_end_local"])
for label in model_labels:
    curve[label] = [row.get(label) for row in curve["models"]]

bom = data["bom_forecast"]
bom_frame = pd.DataFrame(bom.get("rows", []))
has_bom = (bom["status"] == "ok" and not bom_frame.empty
           and "timestamp_local" in bom_frame)
if has_bom:
    bom_frame = bom_frame[bom_frame["timestamp_local"].notna()].copy()
    bom_frame["t"] = pd.to_datetime(bom_frame["timestamp_local"])

figure = make_subplots(rows=2, cols=1, shared_xaxes=True,
                       row_heights=[0.72, 0.28], vertical_spacing=0.06)

figure.add_trace(go.Scatter(
    x=curve["t"], y=curve["p90"], mode="lines", line=dict(width=0),
    showlegend=False, hoverinfo="skip"), row=1, col=1)
figure.add_trace(go.Scatter(
    x=curve["t"], y=curve["p10"], mode="lines", line=dict(width=0),
    fill="tonexty", fillcolor="rgba(42,120,214,0.16)",
    name="ECMWF P10\u2013P90", hoverinfo="skip"), row=1, col=1)

figure.add_trace(go.Scatter(
    x=curve["t"], y=curve["mean"], mode="lines", name="ECMWF mean",
    line=dict(color=ECMWF_COLOUR, width=2.5),
    customdata=curve[["p10", "p90"]],
    hovertemplate="ECMWF mean <b>%{y:.1f} mm</b>"
                  "  (P10\u2013P90 %{customdata[0]:.1f}\u2013"
                  "%{customdata[1]:.1f})<extra></extra>"), row=1, col=1)

for label in model_labels:
    figure.add_trace(go.Scatter(
        x=curve["t"], y=curve[label], mode="lines", name=label,
        line=dict(color=MODEL_COLOURS.get(label, "#888780"), width=1.6,
                  dash=DASHES.get(label, "solid")),
        connectgaps=False,
        hovertemplate=f"{label} <b>%{{y:.1f}} mm</b><extra></extra>"),
        row=1, col=1)

figure.add_hline(y=threshold, line=dict(color="#BA7517", width=1.5,
                                        dash="dash"),
                 annotation_text=f"{GE}{threshold:.0f} mm threshold",
                 annotation_position="top left", row=1, col=1)

if has_bom:
    figure.add_trace(go.Bar(
        x=bom_frame["t"], y=bom_frame.get("mm_10pct"),
        name="BOM 10% >", marker_color="rgba(136,135,128,0.45)",
        hovertemplate="BOM 3 h, 10%% chance of more than "
                      "<b>%{y:.1f} mm</b><extra></extra>"), row=2, col=1)
    figure.add_trace(go.Bar(
        x=bom_frame["t"], y=bom_frame.get("mm_50pct"),
        name="BOM 50% >", marker_color="#5F5E5A",
        hovertemplate="BOM 3 h, 50%% chance of more than "
                      "<b>%{y:.1f} mm</b><extra></extra>"), row=2, col=1)

figure.update_layout(
    height=540, margin=dict(l=10, r=10, t=30, b=10),
    hovermode="x unified", barmode="overlay",
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
figure.update_yaxes(title_text="mm per 24 h", rangemode="tozero",
                    gridcolor="rgba(128,128,128,0.2)", row=1, col=1)
figure.update_yaxes(title_text="BOM 3 h (mm)", rangemode="tozero",
                    gridcolor="rgba(128,128,128,0.2)", row=2, col=1)
figure.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)",
                    dtick=DAY_MS, row=1, col=1)
figure.update_xaxes(title_text="Time (AEST)", showgrid=True,
                    gridcolor="rgba(128,128,128,0.15)",
                    dtick=DAY_MS, tickformat="%a<br>%d %b", row=2, col=1)

st.plotly_chart(figure, width="stretch")

st.markdown(
    "<span class='muted'>Upper panel: each point is the total for the 24 hours "
    "ending at that time, so windows overlap. The shaded band is the ECMWF "
    "P10\u2013P90 range; GFS, UKMO and ICON are single runs with no range.<br>"
    "Lower panel: BOM 3-hourly amounts exactly as published. These are "
    "quantiles, not totals, so they cannot be added together to make a "
    "24-hour figure and are shown on their own axis.</span>",
    unsafe_allow_html=True)

st.divider()

# --- ECMWF table --------------------------------------------------------

daily = data["daily_comparison"]
columns = [row["day_label"] for row in daily]

st.markdown("## ECMWF ensemble by day")

rows = []
index = []
if not rain_day:
    rows.append([row["window_label"] for row in daily])
    index.append("Window (AEST)")
rows += [
    [fmt(row["ecmwf_p10"]) for row in daily],
    [fmt(row["ecmwf_mean"]) for row in daily],
    [fmt(row["ecmwf_p90"]) for row in daily],
    [f"{row['members_over']}/{row['members_total']}" for row in daily],
    [f"{row['percent_over']}%" for row in daily],
]
index += ["P10", "Mean", "P90", f"Members {GE}{threshold:.0f} mm",
          "% of members"]

ecmwf_table = pd.DataFrame(rows, index=index, columns=columns)
st.dataframe(ecmwf_table.style.apply(highlight, limit=threshold, only="Mean",
                                     axis=1), width="stretch")

if rain_day:
    hour = data.get("rain_day_start_hour", 9)
    st.markdown(f"<span class='muted'>Each column is a fixed "
                f"{hour:02d}:00 {ARROW} {hour:02d}:00 AEST rain day, labelled "
                f"by the day it starts, so columns are directly comparable. "
                f"An event straddling {hour:02d}:00 can split across two "
                f"columns and read lower than the rolling maximum above; the "
                f"headline is the authoritative figure. Highlighted where the "
                f"mean reaches {GE}{threshold:.0f} mm.</span>",
                unsafe_allow_html=True)
else:
    st.markdown(f"<span class='muted'>Wettest 24-hour window ending each day. "
                f"End times vary, so a window shown against one day may cover "
                f"the previous one. Highlighted where the mean reaches "
                f"{GE}{threshold:.0f} mm.</span>", unsafe_allow_html=True)

# --- Model comparison ---------------------------------------------------

st.markdown("## Model comparison")

rows = [[fmt(row["ecmwf_mean"]) for row in daily]]
index = ["ECMWF mean"]
for label in model_labels:
    rows.append([fmt(row["models"].get(label)) for row in daily])
    index.append(label)

comparison = pd.DataFrame(rows, index=index, columns=columns)
st.dataframe(comparison.style.apply(highlight, limit=threshold, axis=1),
             width="stretch")
st.markdown(f"<span class='muted'>All models read over the same 24-hour "
            f"window each day, so the columns are directly comparable. "
            f"{DASH} means the model does not reach that window.</span>",
            unsafe_allow_html=True)

# --- BOM table ----------------------------------------------------------

st.markdown("## BOM rainfall forecast")

if bom["status"] != "ok":
    st.markdown("<div class='failed'>Source unavailable</div>",
                unsafe_allow_html=True)
else:
    visible = bom_visible(bom["rows"])
    bom_columns = []
    values = {"Chance of any rain": [], "50% >": [], "25% >": [], "10% >": []}
    for row in visible:
        stamp = row.get("timestamp_local")
        bom_columns.append(f"{pd.Timestamp(stamp):%a %d} {row['time']}"
                           if stamp else f"{row['day'][:3]} {row['time']}")
        chance = row.get("chance_any_rain")
        values["Chance of any rain"].append(
            DASH if chance is None else f"{chance:.0f}%")
        values["50% >"].append(fmt(row.get("mm_50pct")))
        values["25% >"].append(fmt(row.get("mm_25pct")))
        values["10% >"].append(fmt(row.get("mm_10pct")))

    st.dataframe(pd.DataFrame(values, index=bom_columns).T,
                 width="stretch", height=180)
    st.markdown(f"<span class='muted'>As published by BOM, in 3-hourly steps, "
                f"shown to the last step carrying a rainfall amount "
                f"({len(visible)} of {len(bom['rows'])} steps). Later steps "
                f"publish only chance of any rain. Amounts are exceedance "
                f"quantiles: they cannot be summed to a 24-hour total and do "
                f"not feed any calculation above.</span>",
                unsafe_allow_html=True)

st.divider()

# --- Boyd Street, soil moisture, map ------------------------------------

boyd_col, soil_col, map_col = st.columns([2, 2, 3])

with boyd_col:
    st.markdown("### Boyd St drainage channel")
    st.markdown("<span class='muted'>Station 540842. Automated extraction is "
                "not available for this gauge.</span>", unsafe_allow_html=True)
    st.markdown(
        "[Graph](https://www.bom.gov.au/fwo/IDQ65388/IDQ65388.540842.plt.shtml)"
        " \u00b7 "
        "[Table](https://www.bom.gov.au/fwo/IDQ65388/IDQ65388.540842.tbl.shtml)")

with soil_col:
    st.markdown("### Root-zone soil moisture")
    st.markdown("<div class='failed'>Source unavailable</div>",
                unsafe_allow_html=True)
    st.markdown("<span class='muted'>Background context.</span>",
                unsafe_allow_html=True)
    st.markdown("[Australian Water Outlook](https://awo.bom.gov.au/)")

with map_col:
    st.markdown("### Where each model is sampled")

    points = [{
        "label": record["label"],
        "lat": record["grid_point"]["latitude"],
        "lon": record["grid_point"]["longitude"],
        "km": record["grid_point"]["distance_km"],
    } for record in data["sources"].values()
        if record["status"] == "ok" and record.get("grid_point")]

    if points:
        grid_frame = pd.DataFrame(points)
        site = go.Figure()
        site.add_trace(go.Scattermap(
            lat=grid_frame["lat"], lon=grid_frame["lon"],
            mode="markers+text", text=grid_frame["label"],
            textposition="top right",
            textfont=dict(size=11, color="#ffffff"),
            marker=dict(size=11, color="#2a78d6"),
            customdata=grid_frame["km"],
            hovertemplate="%{text}<br>%{customdata:.1f} km from the airport"
                          "<extra></extra>", showlegend=False))
        site.add_trace(go.Scattermap(
            lat=[config.LATITUDE], lon=[config.LONGITUDE],
            mode="markers+text", text=["Gold Coast Airport"],
            textposition="bottom right",
            textfont=dict(size=11, color="#ffd27f"),
            marker=dict(size=13, color="#eb6834"),
            hoverinfo="text", showlegend=False))

        map_config = dict(
            center=dict(lat=config.LATITUDE, lon=config.LONGITUDE),
            zoom=config.MAP_ZOOM)
        if getattr(config, "MAP_TILES", None):
            map_config["style"] = "white-bg"
            map_config["layers"] = [dict(
                below="traces", sourcetype="raster",
                sourceattribution=config.MAP_ATTRIBUTION,
                source=[config.MAP_TILES])]
        else:
            map_config["style"] = "open-street-map"

        site.update_layout(map=map_config, height=330,
                           margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(site, width="stretch")
        st.markdown("<span class='muted'>Global models hold values at grid "
                    "cell centres, not at the airport. Distances of "
                    "7\u201318 km are normal for a 24-hour regional rainfall "
                    "question.</span>", unsafe_allow_html=True)

st.divider()

# --- Sources ------------------------------------------------------------

st.markdown("## Data sources")

source_rows = []
for record in data["sources"].values():
    grid = record.get("grid_point") or {}
    retrieved = pd.Timestamp(record["retrieved_at_utc"]).tz_convert(
        config.LOCAL_TZ)
    source_rows.append({
        "Source": record["label"],
        "Centre": record.get("centre", record.get("location", "BOM")),
        "Status": "ok" if record["status"] == "ok" else "unavailable",
        "Distance": f"{grid['distance_km']:.1f} km" if grid else DASH,
        "Retrieved": f"{retrieved:%a %d %b %H:%M}",
    })

st.dataframe(pd.DataFrame(source_rows), hide_index=True, width="stretch")

st.markdown(" \u00b7 ".join(f"[{item['label']}]({item['url']})"
                            for item in config.REFERENCE_LINKS))

unavailable = ", ".join(f"{m['label']} ({m['centre']})"
                        for m in data["unavailable_models"])
st.markdown(f"<span class='muted'>Not currently available: {unavailable}. "
            f"ACCESS-C requires a paid BOM Registered User subscription."
            f"<br>{data['attribution']}</span>", unsafe_allow_html=True)