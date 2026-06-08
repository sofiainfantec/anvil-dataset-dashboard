from pathlib import Path
from datetime import datetime, timedelta
import os
import json

import pandas as pd
import streamlit as st
import plotly.express as px
import yaml


DEFAULT_RECORDINGS_PATH = (
    Path.home()
    / "anvil-loader"
    / "data"
    / "recordings"
)

RECORDINGS_PATH = Path(
    os.getenv("RECORDINGS_PATH", str(DEFAULT_RECORDINGS_PATH))
)

OUTPUT_FILE = (
    Path.home()
    / "Documents"
    / "robotics_reports"
    / "anvil_recordings_summary.csv"
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


def find_created_time(metadata, episode_path):
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

    return datetime.fromtimestamp(episode_path.stat().st_mtime)


def load_recordings(recordings_path):
    records = []

    session_dirs = [
        p for p in recordings_path.iterdir()
        if p.is_dir()
    ]

    for session_dir in sorted(session_dirs):
        session_name = session_dir.name

        episode_dirs = [
            p for p in session_dir.iterdir()
            if p.is_dir()
        ]

        for episode_dir in sorted(episode_dirs):
            episode_name = episode_dir.name

            json_metadata = read_json(episode_dir / "metadata.json")
            yaml_metadata = read_yaml(episode_dir / "metadata.yaml")

            metadata = {}
            metadata.update(yaml_metadata)
            metadata.update(json_metadata)

            mcap_files = sorted(episode_dir.glob("*.mcap"))
            mcap_count = len(mcap_files)

            duration_seconds = find_duration_seconds(metadata)

            if duration_seconds is None:
                duration_seconds = None

            created_time = find_created_time(metadata, episode_dir)
            updated_time = datetime.fromtimestamp(episode_dir.stat().st_mtime)

            records.append({
                "session": session_name,
                "episode": episode_name,
                "duration_seconds": duration_seconds,
                "duration": format_duration(duration_seconds),
                "created_time": created_time,
                "updated_time": updated_time,
                "mcap_count": mcap_count,
                "episode_path": str(episode_dir),
            })

    df = pd.DataFrame(records)

    if not df.empty:
        df = df.sort_values("created_time").reset_index(drop=True)

        df["previous_session"] = df["session"].shift(1)
        df["previous_episode"] = df["episode"].shift(1)
        df["previous_updated_time"] = df["updated_time"].shift(1)

        df["setup_time_seconds"] = (
            df["created_time"] - df["previous_updated_time"]
        ).dt.total_seconds()

        df.loc[df["setup_time_seconds"] < 0, "setup_time_seconds"] = 0
        df["setup_time"] = df["setup_time_seconds"].apply(format_duration)

    return df


st.set_page_config(
    page_title="Anvil Recordings Dashboard",
    layout="wide",
)

st.title("Anvil Recordings Dashboard")

recordings_path_input = st.text_input(
    "Recordings path",
    value=str(RECORDINGS_PATH),
)

recordings_path = Path(recordings_path_input)

if not recordings_path.exists():
    st.warning("Recordings path does not exist.")
    st.stop()

df = load_recordings(recordings_path)

if df.empty:
    st.warning("No recordings found.")
    st.stop()


if st.button("Export CSV"):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    st.success(f"CSV exported to: {OUTPUT_FILE}")


duration_df = df.dropna(subset=["duration_seconds"])
setup_df = df.dropna(subset=["setup_time_seconds"])

total_recordings = len(df)
total_sessions = df["session"].nunique()
total_recording_time = duration_df["duration_seconds"].sum()
typical_duration = duration_df["duration_seconds"].median()

if not duration_df.empty:
    longest = duration_df.loc[duration_df["duration_seconds"].idxmax()]
    shortest = duration_df.loc[duration_df["duration_seconds"].idxmin()]
else:
    longest = None
    shortest = None

avg_setup_time = setup_df["setup_time_seconds"].mean()
total_setup_time = setup_df["setup_time_seconds"].sum()
total_session_time = total_recording_time + total_setup_time

recording_utilization = (
    total_recording_time / total_session_time * 100
    if total_session_time > 0
    else 0
)


st.subheader("Recording Summary")

col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("Total Sessions", total_sessions)
col2.metric("Total Recordings", total_recordings)
col3.metric("Total Recording Time", format_duration(total_recording_time))
col4.metric("Typical Duration", format_duration(typical_duration))
col5.metric("Longest Recording", longest["duration"] if longest is not None else "N/A")
col6.metric("Shortest Recording", shortest["duration"] if shortest is not None else "N/A")

st.divider()


st.subheader("Operational Efficiency")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Average Setup Time", format_duration(avg_setup_time))
col2.metric("Total Setup Time", format_duration(total_setup_time))
col3.metric("Total Session Time", format_duration(total_session_time))
col4.metric("Recording Utilization", f"{recording_utilization:.1f}%")

st.divider()


st.subheader("Recordings by Session")

session_summary = (
    df.groupby("session")
    .agg(
        recordings=("episode", "count"),
        total_recording_seconds=("duration_seconds", "sum"),
        typical_duration_seconds=("duration_seconds", "median"),
    )
    .reset_index()
)

session_summary["total_recording_time"] = session_summary[
    "total_recording_seconds"
].apply(format_duration)

session_summary["typical_duration"] = session_summary[
    "typical_duration_seconds"
].apply(format_duration)

st.dataframe(
    session_summary[
        [
            "session",
            "recordings",
            "total_recording_time",
            "typical_duration",
        ]
    ],
    use_container_width=True,
)

fig_sessions = px.bar(
    session_summary,
    x="session",
    y="recordings",
    title="Recordings per Session",
)

st.plotly_chart(fig_sessions, use_container_width=True)


if not duration_df.empty:
    st.subheader("Recording Duration Distribution")

    fig_duration = px.histogram(
        duration_df,
        x="duration_seconds",
        nbins=20,
        title="Distribution of Recording Duration",
    )

    st.plotly_chart(fig_duration, use_container_width=True)


st.subheader("Longest Recordings")

if duration_df.empty:
    st.info("No duration data available.")
else:
    st.dataframe(
        duration_df.sort_values("duration_seconds", ascending=False)
        [["session", "episode", "duration"]]
        .head(10),
        use_container_width=True,
    )


st.subheader("Shortest Recordings")

if duration_df.empty:
    st.info("No duration data available.")
else:
    st.dataframe(
        duration_df.sort_values("duration_seconds", ascending=True)
        [["session", "episode", "duration"]]
        .head(10),
        use_container_width=True,
    )


st.subheader("Longest Setup Times")

st.dataframe(
    setup_df.sort_values("setup_time_seconds", ascending=False)
    [["previous_session", "previous_episode", "session", "episode", "setup_time"]]
    .head(10),
    use_container_width=True,
)


st.subheader("Shortest Setup Times")

st.dataframe(
    setup_df.sort_values("setup_time_seconds", ascending=True)
    [["previous_session", "previous_episode", "session", "episode", "setup_time"]]
    .head(10),
    use_container_width=True,
)


st.subheader("All Recordings")

st.dataframe(
    df[
        [
            "session",
            "episode",
            "duration",
            "setup_time",
            "created_time",
            "updated_time",
            "mcap_count",
        ]
    ],
    use_container_width=True,
)
