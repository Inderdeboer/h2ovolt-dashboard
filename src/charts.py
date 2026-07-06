from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.calculations import smooth

PRIMARY_BLUE = "#0057B8"
COLOR_PV = "#D9A441"
COLOR_BUILDING = "#B85C5C"
COLOR_BATTERY = "#7FB069"
COLOR_GRID = "#5B6AA5"
COLOR_AVOIDED = "rgba(126, 220, 138, 0.26)"
COLOR_STILL_ABOVE = "rgba(217, 164, 65, 0.26)"
COLOR_SOC_MIN = "#FF9F1C"


def _add_fill_between_segments(
    fig: go.Figure,
    *,
    x: pd.Series,
    lower: pd.Series,
    upper: pd.Series,
    condition: pd.Series,
    name: str,
    color: str,
    row: int | None = None,
    col: int | None = None,
    secondary_y: bool | None = None,
    min_delta: float = 0.05,
) -> None:
    """
    Robust Plotly fill_between replacement.

    The first app version used fill='tonexty' with NaNs. That can look glitched
    with many gaps, dual y-axes, and disconnected time periods. This version
    creates separate closed polygons for each continuous valid interval.
    """
    fill_df = pd.DataFrame(
        {
            "x": x.reset_index(drop=True),
            "lower": lower.reset_index(drop=True),
            "upper": upper.reset_index(drop=True),
            "condition": condition.reset_index(drop=True),
        }
    ).dropna(subset=["x", "lower", "upper"])

    if fill_df.empty:
        return

    fill_df["condition"] = fill_df["condition"].fillna(False).astype(bool)
    fill_df["condition"] &= (fill_df["upper"] - fill_df["lower"]) > min_delta

    # Also break the fill when there is a large timestamp gap.
    dt = fill_df["x"].diff()
    normal_dt = dt[dt > pd.Timedelta(0)].median()
    if pd.isna(normal_dt):
        normal_dt = pd.Timedelta(minutes=5)
    max_allowed_gap = normal_dt * 3

    segment_id = ((~fill_df["condition"]) | (dt > max_allowed_gap)).cumsum()
    showlegend = True

    for _, segment in fill_df[fill_df["condition"]].groupby(segment_id):
        if len(segment) < 2:
            continue

        trace = go.Scatter(
            x=list(segment["x"]) + list(segment["x"])[::-1],
            y=list(segment["upper"]) + list(segment["lower"])[::-1],
            fill="toself",
            fillcolor=color,
            line=dict(width=0, color="rgba(255,255,255,0)"),
            mode="lines",
            hoverinfo="skip",
            name=name,
            legendgroup=name,
            showlegend=showlegend,
        )
        showlegend = False

        if row is None or col is None:
            fig.add_trace(trace)
        else:
            fig.add_trace(trace, row=row, col=col, secondary_y=secondary_y)


def _base_layout(fig: go.Figure, title: str, height: int = 640) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left"),
        height=height,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
            groupclick="togglegroup",
        ),
        margin=dict(l=20, r=20, t=64, b=120),
    )
    fig.update_xaxes(title_text="Time", showgrid=False)
    return fig


def build_peak_shaving_chart(df: pd.DataFrame, *, smooth_window: int = 15) -> go.Figure:
    plot_df = df.copy()
    x = plot_df["Timestamp"]

    import_with_s = smooth(plot_df["Import_with_battery_kW"], smooth_window)
    import_without_s = smooth(plot_df["Import_without_battery_kW"], smooth_window)
    battery_power_s = smooth(plot_df["Battery_kW"], smooth_window)
    desired_peak_s = smooth(plot_df["DesiredPeakPower_kW"], min(max(1, smooth_window), 6))

    battery_avoided = (import_without_s > desired_peak_s) & (import_with_s <= desired_peak_s)
    still_above = import_with_s > desired_peak_s

    fig = go.Figure()

    _add_fill_between_segments(
        fig,
        x=x,
        lower=desired_peak_s,
        upper=import_without_s,
        condition=battery_avoided,
        name="Exceedance avoided by battery",
        color=COLOR_AVOIDED,
    )
    _add_fill_between_segments(
        fig,
        x=x,
        lower=desired_peak_s,
        upper=import_with_s,
        condition=still_above,
        name="Still above maximum power",
        color=COLOR_STILL_ABOVE,
    )

    fig.add_trace(go.Scatter(x=x, y=import_without_s, mode="lines", name="Net import without battery", line=dict(color=COLOR_BUILDING, width=2.4)))
    fig.add_trace(go.Scatter(x=x, y=import_with_s, mode="lines", name="Net import with battery", line=dict(color=COLOR_BATTERY, width=2.8)))
    if plot_df["DesiredPeakPower_kW"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=desired_peak_s, mode="lines", name="Desired peak power", line=dict(color=COLOR_GRID, width=2.0, dash="dash")))
    fig.add_trace(go.Scatter(x=x, y=battery_power_s, mode="lines", name="Battery power", line=dict(color=PRIMARY_BLUE, width=1.8, dash="dot")))

    _base_layout(fig, "Peak shaving - net import versus maximum power")
    fig.update_yaxes(title_text="Power / net import (kW)", gridcolor="rgba(0,0,0,.08)")
    return fig


def build_load_balancing_chart(df: pd.DataFrame, *, smooth_window: int = 30, show_soc_min: bool = False) -> go.Figure:
    plot_df = df.copy()
    x = plot_df["Timestamp"]

    import_with_s = smooth(plot_df["Import_with_battery_kW"], smooth_window)
    import_without_s = smooth(plot_df["Import_without_battery_kW"], smooth_window)
    soc_s = smooth(plot_df["Soc"], min(max(1, smooth_window), 6))
    soc_min_s = smooth(plot_df["SOCMinLoadProfile"], min(max(1, smooth_window), 6))

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    _add_fill_between_segments(
        fig,
        x=x,
        lower=import_with_s,
        upper=import_without_s,
        condition=import_without_s > import_with_s,
        name="Avoided grid import",
        color=COLOR_AVOIDED,
        row=1,
        col=1,
        secondary_y=False,
    )

    fig.add_trace(go.Scatter(x=x, y=import_without_s, mode="lines", name="Net import without battery", line=dict(color=COLOR_BUILDING, width=2.4)), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=import_with_s, mode="lines", name="Net import with battery", line=dict(color=COLOR_BATTERY, width=2.8)), secondary_y=False)

    if plot_df["Soc"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=soc_s, mode="lines", name="SOC", line=dict(color=COLOR_GRID, width=2.0)), secondary_y=True)

    if show_soc_min and plot_df["SOCMinLoadProfile"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=soc_min_s, mode="lines", name="Minimum SOC", line=dict(color=COLOR_SOC_MIN, width=1.8, dash="dash")), secondary_y=True)

    _base_layout(fig, "Load balancing - net import with and without battery")
    fig.update_yaxes(title_text="Power (kW)", gridcolor="rgba(0,0,0,.08)", secondary_y=False)
    fig.update_yaxes(title_text="SOC (%)", range=[0, 100], secondary_y=True)
    return fig


def build_battery_power_chart(df: pd.DataFrame, *, smooth_window: int = 15) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Timestamp"], y=smooth(df["Battery_kW"], smooth_window), mode="lines", name="Battery power", line=dict(color=PRIMARY_BLUE, width=2.2)))
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="rgba(0,0,0,.35)")
    _base_layout(fig, "Battery power")
    fig.update_yaxes(title_text="kW")
    return fig
