from pathlib import Path
from datetime import datetime, timedelta
import os
import json

import pandas as pd
import streamlit as st
import plotly.express as px
import yaml


DEFAULT_SESSION_PATH = (
    Path.home()
    / "anvil-loader"
    / "data"
    / "recordings"
    / "organize-the-table"
)

SESSION_PATH = Path(
    os.getenv("RECORDINGS_PATH", str(DEFAULT_SESSION_PATH))
)

OUTPUT_FILE = (
    Path.home()
    / "Documents"
    / "robotics_reports"
    / "anvil_session_summary.csv"
)


def format_duration(seconds):
    if pd.isna(seconds):
        return "N/A"
    return str(timedelta(seconds=round(float(seconds))))


def read_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def read_yaml(path):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def find_duration_seconds(metadata):
    possible_keys = [
        "duration",
        "duration_seconds",
        "recording_duration",
        "elapsed_time",
        "total_duration",
    ]

    for key in possible_keys:
        value = metadata.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    return None


def find_created_time(metadata, recording_path):
    possible_keys = [
        "created",
        "created_at",
        "start_time",
        "started_at",
        "timestamp",
    ]

    for key in possible_keys:
        value = metadata.get(key)
        if isinstance(value, str):
            try:
                return pd.to_datetime(value).to_pydatetime()
            except Exception:
                pass

    return datetime.fromtimestamp(recording_path.stat().st_mtime)


def load_session(session_path):
    records = []

    recording_dirs = [
        p for p in session_path.iterdir()
        if p.is_dir() and p.name.isdigit()
    ]

    for recording_dir in sorted(recording_dirs):
        recording_name = recording_dir.name

        json_metadata = read_json(recording_dir / "metadata.json")
        yaml_metadata = read_yaml(recording_dir / "metadata.yaml")

        metadata = {}
        metadata.update(yaml_metadata)
        metadata.update(json_metadata)

        mcap_files = sorted(recording_dir.glob("*.mcap"))

        duration_seconds = find_duration_seconds(metadata)

        created_time = find_created_time(metadata, recording_dir)
        updated_time = datetime.fromtimestamp(recording_dir.stat().st_mtime)

        records.append(
            {
                "recording": recording_name,
                "duration_seconds": duration_seconds,
                "duration": format_duration(duration_seconds),
                "created_time": created_time,
                "updated_time": updated_time,
                "mcap_count": len(mcap_files),
            }
        )

    df = pd.DataFrame(records)

    if not df.empty:
        df = df.sort_values("created_time").reset_index(drop=True)

        df["previous_recording"] = df["recording"].shift(1)
        df["previous_updated_time"] = df["updated_time"].shift(1)

        df["setup_time_seconds"] = (
            df["created_time"] - df["previous_updated_time"]
        ).dt.total_seconds()

        df.loc[df["setup_time_seconds"] < 0, "setup_time_seconds"] = 0
        df["setup_time"] = df["setup_time_seconds"].apply(format_duration)

    return df


st.set_page_config(
    page_title="Anvil Session Dashboard",
    layout="wide",
)

session_name = SESSION_PATH.name

st.title(session_name)

df = load_session(SESSION_PATH)

if df.empty:
    st.warning("No recordings found. Make sure RECORDINGS_PATH points to a session folder.")
    st.stop()


if st.button("Export CSV"):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    st.success(f"CSV exported to: {OUTPUT_FILE}")


duration_df = df.dropna(subset=["duration_seconds"])
setup_df = df.dropna(subset=["setup_time_seconds"])

total_recordings = len(df)
total_recording_time = duration_df["duration_seconds"].sum()
typical_duration = duration_df["duration_seconds"].median()

longest = duration_df.loc[duration_df["duration_seconds"].idxmax()]
shortest = duration_df.loc[duration_df["duration_seconds"].idxmin()]

avg_setup_time = setup_df["setup_time_seconds"].mean()
total_setup_time = setup_df["setup_time_seconds"].sum()
total_session_time = total_recording_time + total_setup_time

recording_utilization = (
    total_recording_time / total_session_time * 100
    if total_session_time > 0
    else 0
)


st.subheader("Recording Summary")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Recordings", total_recordings)
col2.metric("Total Recording Time", format_duration(total_recording_time))
col3.metric("Typical Duration", format_duration(typical_duration))
col4.metric("Longest Recording", longest["duration"])
col5.metric("Shortest Recording", shortest["duration"])

st.divider()


st.subheader("Operational Efficiency")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Average Setup Time", format_duration(avg_setup_time))
col2.metric("Total Setup Time", format_duration(total_setup_time))
col3.metric("Total Session Time", format_duration(total_session_time))
col4.metric("Recording Utilization", f"{recording_utilization:.1f}%")

st.divider()


st.subheader("Recording Duration Trend")

plot_df = df.copy()
plot_df["recording_index"] = range(1, len(plot_df) + 1)

median_duration = plot_df["duration_seconds"].median()

fig = px.scatter(
    plot_df,
    x="recording_index",
    y="duration_seconds",
    hover_data=["recording", "duration"],
    title="Recording Duration by Recording",
    labels={
        "recording_index": "Recording",
        "duration_seconds": "Duration (seconds)",
    },
)

fig.update_traces(mode="markers+lines")

fig.add_hline(
    y=median_duration,
    line_dash="dash",
    annotation_text=f"Median: {format_duration(median_duration)}",
    annotation_position="top left",
)

st.plotly_chart(fig, use_container_width=True)


st.subheader("Longest Recordings")

st.dataframe(
    duration_df.sort_values("duration_seconds", ascending=False)
    [["recording", "duration"]]
    .head(10),
    use_container_width=True,
)


st.subheader("Shortest Recordings")

st.dataframe(
    duration_df.sort_values("duration_seconds", ascending=True)
    [["recording", "duration"]]
    .head(10),
    use_container_width=True,
)


st.subheader("Longest Setup Times")

st.dataframe(
    setup_df.sort_values("setup_time_seconds", ascending=False)
    [["previous_recording", "recording", "setup_time"]]
    .head(10),
    use_container_width=True,
)


st.subheader("Shortest Setup Times")

st.dataframe(
    setup_df.sort_values("setup_time_seconds", ascending=True)
    [["previous_recording", "recording", "setup_time"]]
    .head(10),
    use_container_width=True,
)


st.subheader("All Recordings")

st.dataframe(
    df[
        [
            "recording",
            "duration",
            "setup_time",
            "created_time",
            "updated_time",
            "mcap_count",
        ]
    ],
    use_container_width=True,
)
