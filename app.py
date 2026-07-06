from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.calculations import (
    CalculationOptions,
    add_core_calculations,
    filter_timeframe,
    summarize_load_balancing,
    summarize_peak_shaving,
)
from src.charts import (
    build_battery_power_chart,
    build_load_balancing_chart,
    build_peak_shaving_chart,
)
from src.data_loader import (
    battery_name_from_excel,
    clean_ems_dataframe,
    find_excel_files,
    load_raw_excel_from_path,
    load_raw_excel_from_upload,
)
from src.ui import dataclass_to_frame, fmt_hours, fmt_kwh, fmt_kw, metric_grid


st.set_page_config(
    page_title="H2OVolt Dashboard Demo",
    page_icon="🔋",
    layout="wide",
)

st.title("H2OVolt Dashboard Demo")
st.caption("Demo dashboard for viewing EMS data with the existing peak shaving and load balancing calculations.")


# =============================================================================
# Sidebar controls
# =============================================================================
st.sidebar.title("Controls")
st.sidebar.subheader("Data source")

DEFAULT_DATA_FOLDER = Path(__file__).resolve().parent / "data"
folder_path = st.sidebar.text_input(
    "Data folder path",
    value=str(DEFAULT_DATA_FOLDER),
    help="Paste the folder that contains the EMS Excel files. The app only opens the selected file, not every Excel in the folder.",
)

excel_files = find_excel_files(folder_path.strip().strip('"')) if folder_path.strip() else []

selected_excel_path: str | None = None
source_label = ""

if excel_files:
    options = [f"{item['name']}  ({item['filename']})" for item in excel_files]
    selected_index = st.sidebar.selectbox("Battery / Excel file", range(len(options)), format_func=lambda i: options[i])
    selected_item = excel_files[int(selected_index)]
    selected_excel_path = selected_item["path"]
    source_label = f"{selected_item['name']} ({selected_item['filename']})"
    st.sidebar.caption(f"Found {len(excel_files)} Excel file(s). Only the selected file is loaded.")
else:
    st.sidebar.warning("No Excel files found in this folder yet.")

uploaded_file = st.sidebar.file_uploader(
    "Or upload one EMS Excel file",
    type=["xlsx", "xls"],
    help="Upload is optional. If uploaded, this file is used instead of the folder selection.",
)

st.sidebar.divider()
st.sidebar.subheader("Calculation settings")

battery_connection = st.sidebar.selectbox(
    "Battery connection",
    ["parallel", "series"],
    index=0,
    help=(
        "Parallel subtracts AC-out as battery standby usage. "
        "Series uses raw discharge directly because all site power passes through AC-out."
    ),
)

flip_battery_sign = st.sidebar.toggle(
    "Flip battery sign",
    value=False,
    help="Turn this on only if the battery current sign is opposite in a file.",
)

show_soc_min = st.sidebar.toggle("Show minimum SOC", value=False)
peak_smooth = st.sidebar.slider("Peak shaving smoothing window", 1, 90, 15)
load_smooth = st.sidebar.slider("View smoothing window", 1, 120, 30)

if st.sidebar.button("Refresh cached data"):
    st.cache_data.clear()
    st.rerun()


# =============================================================================
# Load + clean selected data only
# =============================================================================
raw_df: pd.DataFrame | None = None

try:
    if uploaded_file is not None:
        with st.spinner(f"Loading uploaded file {uploaded_file.name}..."):
            raw_df = load_raw_excel_from_upload(uploaded_file.getvalue())
        source_label = uploaded_file.name
    elif selected_excel_path:
        excel_path = Path(selected_excel_path)
        with st.spinner(f"Loading selected Excel file: {excel_path.name}..."):
            raw_df = load_raw_excel_from_path(excel_path)
        if not source_label:
            source_label = f"{battery_name_from_excel(excel_path)} ({excel_path.name})"
    else:
        st.info("Paste the data folder path in the sidebar, then choose one battery file.")
        st.stop()

    with st.spinner("Cleaning EMS data..."):
        clean_df, clean_info = clean_ems_dataframe(raw_df)
except Exception as exc:
    st.error(str(exc))
    st.stop()

if clean_df.empty:
    st.warning("The file loaded, but no usable rows remained after cleaning.")
    st.stop()

min_date = clean_df["Timestamp"].min().date()
max_date = clean_df["Timestamp"].max().date()


# =============================================================================
# Date selector before calculations/plotting
# =============================================================================
st.sidebar.divider()
st.sidebar.subheader("Date selector")

quick_range = st.sidebar.selectbox(
    "Quick range",
    ["Single day", "Last 7 days", "Last 30 days", "Custom range", "Full dataset"],
    index=1,
)

if quick_range == "Single day":
    single_day = st.sidebar.date_input("Day", value=max_date, min_value=min_date, max_value=max_date)
    selected_clean_df = filter_timeframe(
        clean_df,
        mode="Single day",
        single_day=single_day,
        start_date=single_day,
        end_date=single_day,
        last_days=1,
    )
elif quick_range == "Last 7 days":
    selected_clean_df = filter_timeframe(
        clean_df,
        mode="Last N days",
        single_day=max_date,
        start_date=min_date,
        end_date=max_date,
        last_days=7,
    )
elif quick_range == "Last 30 days":
    selected_clean_df = filter_timeframe(
        clean_df,
        mode="Last N days",
        single_day=max_date,
        start_date=min_date,
        end_date=max_date,
        last_days=30,
    )
elif quick_range == "Custom range":
    range_value = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(range_value, tuple):
        if len(range_value) == 2:
            start_date, end_date = range_value
        elif len(range_value) == 1:
            start_date = end_date = range_value[0]
        else:
            start_date, end_date = min_date, max_date
    else:
        start_date = end_date = range_value

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    selected_clean_df = filter_timeframe(
        clean_df,
        mode="Date range",
        single_day=end_date,
        start_date=start_date,
        end_date=end_date,
        last_days=7,
    )
else:
    selected_clean_df = filter_timeframe(
        clean_df,
        mode="Full dataset",
        single_day=max_date,
        start_date=min_date,
        end_date=max_date,
        last_days=7,
    )

if selected_clean_df.empty:
    st.warning("No rows found for the selected date range. Choose a wider range.")
    st.stop()

with st.spinner("Calculating and preparing Plotly views..."):
    options = CalculationOptions(
        battery_power_enabled=True,
        flip_battery_sign=flip_battery_sign,
        battery_connection=battery_connection,
    )
    selected_df = add_core_calculations(selected_clean_df, options)
    peak_summary = summarize_peak_shaving(selected_df)
    load_summary = summarize_load_balancing(selected_df)


# =============================================================================
# Header/status
# =============================================================================
status_cols = st.columns(4)
status_cols[0].metric("File", source_label)
status_cols[1].metric("Rows shown", f"{len(selected_df):,}".replace(",", " "))
status_cols[2].metric("From", f"{selected_df['Timestamp'].min():%d-%m-%Y %H:%M}")
status_cols[3].metric("To", f"{selected_df['Timestamp'].max():%d-%m-%Y %H:%M}")

optional_warnings = []
if selected_df["DesiredPeakPower_kW"].isna().all():
    optional_warnings.append("DesiredPeakPowerKw is missing or 0, so the peak setting is not activated.")
if selected_df["Soc"].isna().all():
    optional_warnings.append("Soc is missing, so the SOC line cannot be shown.")
for warning in optional_warnings:
    st.warning(warning)


# =============================================================================
# Views - keep Plotly plots
# =============================================================================
overview_tab, power_tab, peak_tab, load_tab, data_tab = st.tabs(
    ["Overview", "Power view", "Peak shaving", "Load balancing", "Data"]
)

with overview_tab:
    st.subheader("Key results")
    overview_metric_items = [
        ("Peak reduction", fmt_kw(peak_summary.avoided_peak_kw), None),
        ("Avoided grid import", fmt_kwh(load_summary.import_saved_kwh), None),
        ("Requested from grid", fmt_kwh(load_summary.total_import_with_kwh), None),
        ("Gave back to grid", fmt_kwh(load_summary.total_export_with_kwh), None),
        ("PV generated", fmt_kwh(load_summary.total_pv_generated_kwh), None),
        ("PV into battery", fmt_kwh(load_summary.total_pv_to_battery_kwh), None),
        ("Useful battery support", fmt_kwh(load_summary.total_useful_battery_support_kwh), None),
        ("Raw battery discharge", fmt_kwh(peak_summary.total_raw_discharge_kwh), None),
    ]
    metric_grid(overview_metric_items, columns=4)

    st.plotly_chart(
        build_load_balancing_chart(selected_df, smooth_window=load_smooth, show_soc_min=show_soc_min),
        width="stretch",
        key="overview_load_balancing_chart",
    )

with power_tab:
    st.subheader("Battery power")
    st.plotly_chart(
        build_battery_power_chart(selected_df, smooth_window=peak_smooth),
        width="stretch",
        key="power_battery_power_chart",
    )

with peak_tab:
    st.subheader("Peak shaving")
    metric_grid(
        [
            ("Battery connection", battery_connection.title(), None),
            ("Desired peak power", fmt_kw(peak_summary.desired_peak_power_kw), None),
            ("Peak 15-min avg with battery", fmt_kw(peak_summary.peak_with_kw), None),
            ("Peak 15-min avg without battery", fmt_kw(peak_summary.peak_without_kw), None),
            ("Peak reduction", fmt_kw(peak_summary.avoided_peak_kw), None),
            ("Max exceedance with battery", fmt_kw(peak_summary.max_exceed_with_kw), None),
            ("Max exceedance without battery", fmt_kw(peak_summary.max_exceed_without_kw), None),
            ("Avoided exceedance", fmt_kw(peak_summary.avoided_exceed_kw), None),
            ("Time above desired peak with battery", fmt_hours(peak_summary.time_above_with_h), None),
            ("Time above desired peak without battery", fmt_hours(peak_summary.time_above_without_h), None),
        ],
        columns=5,
    )
    st.plotly_chart(
        build_peak_shaving_chart(selected_df, smooth_window=peak_smooth),
        width="stretch",
        key="peak_shaving_chart",
    )
    with st.expander("Peak shaving summary table"):
        st.dataframe(dataclass_to_frame(peak_summary), use_container_width=True, hide_index=True)

with load_tab:
    st.subheader("Load balancing")
    metric_grid(
        [
            ("Requested from grid", fmt_kwh(load_summary.total_import_with_kwh), None),
            ("Gave back to grid", fmt_kwh(load_summary.total_export_with_kwh), None),
            ("Total import without battery", fmt_kwh(load_summary.total_import_without_kwh), None),
            ("Avoided grid import", fmt_kwh(load_summary.import_saved_kwh), None),
            ("PV generated", fmt_kwh(load_summary.total_pv_generated_kwh), None),
            ("PV into battery", fmt_kwh(load_summary.total_pv_to_battery_kwh), None),
            ("Useful battery support", fmt_kwh(load_summary.total_useful_battery_support_kwh), None),
            ("Battery standby usage", fmt_kwh(load_summary.total_battery_standby_kwh), None),
        ],
        columns=4,
    )
    st.plotly_chart(
        build_load_balancing_chart(selected_df, smooth_window=load_smooth, show_soc_min=show_soc_min),
        width="stretch",
        key="load_balancing_chart",
    )
    with st.expander("Load balancing summary table"):
        st.dataframe(dataclass_to_frame(load_summary), use_container_width=True, hide_index=True)

with data_tab:
    st.subheader("Calculated data preview")
    important_cols = [
        "Timestamp",
        "Grid_kW",
        "PV_kW",
        "Import_with_battery_kW",
        "Export_with_battery_kW",
        "Import_without_battery_kW",
        "Import_with_battery_15min_avg_kW",
        "Import_without_battery_15min_avg_kW",
        "Exceed_with_15min_kW",
        "Exceed_without_15min_kW",
        "Battery_kW",
        "Battery_kW_raw",
        "Battery_charge_raw_kW",
        "Battery_support_kW",
        "Battery_standby_compensated_kW",
        "Battery_standby_kW",
        "Battery_discharge_raw_kW",
        "PV_to_battery_kW",
        "Soc",
        "SOCMinLoadProfile",
        "DesiredPeakPower_kW",
        "dt_h",
        "Import_saved_kWh",
        "PV_generated_kWh",
        "PV_to_battery_kWh",
        "Export_with_battery_kWh",
        "Battery_support_kWh",
        "Battery_discharge_raw_kWh",
        "Battery_charge_raw_kWh",
        "Battery_standby_compensated_kWh",
        "Battery_standby_kWh",
    ]
    visible_cols = [col for col in important_cols if col in selected_df.columns]
    st.dataframe(selected_df[visible_cols].tail(2500), use_container_width=True)

    with st.expander("Raw loaded columns and cleaning info"):
        st.write(clean_info["available_columns"])
        st.json({key: value for key, value in clean_info.items() if key != "available_columns"})
