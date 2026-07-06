from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from typing import Any

import pandas as pd
import streamlit as st


def apply_app_style() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 1.35rem;
                padding-bottom: 2.2rem;
            }
            section[data-testid="stSidebar"] {
                background: #F8FAFC;
            }
            .h2ovolt-hero {
                border-radius: 26px;
                padding: 1.35rem 1.6rem;
                margin-bottom: 1.2rem;
                color: white;
                background: linear-gradient(135deg, #06182F 0%, #0B3C73 55%, #0057B8 100%);
                box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
            }
            .h2ovolt-hero h1 {
                margin: 0;
                font-size: 2.25rem;
                line-height: 1.1;
                letter-spacing: -0.03em;
            }
            .h2ovolt-hero p {
                margin: 0.48rem 0 0 0;
                color: rgba(255,255,255,0.82);
                font-size: 1.02rem;
            }
            div[data-testid="stMetric"] {
                background: #FFFFFF;
                border: 1px solid #E9EEF5;
                padding: 1rem 1rem;
                border-radius: 20px;
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
            }
            .status-card {
                background: #FFFFFF;
                border: 1px solid #E9EEF5;
                border-radius: 20px;
                padding: 1rem 1.1rem;
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.05);
            }
            .status-card strong {
                color: #111827;
            }
            .muted {
                color: #6B7280;
                font-size: 0.9rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    st.markdown(
        """
        <div class="h2ovolt-hero">
            <h1>H2OVolt Battery Dashboard</h1>
            <p>Local Streamlit prototype for peak shaving and load balancing analysis.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt_number(value: float, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", " ")


def fmt_kw(value: float) -> str:
    return f"{fmt_number(value, 2)} kW" if fmt_number(value, 2) != "—" else "—"


def fmt_kwh(value: float) -> str:
    return f"{fmt_number(value, 2)} kWh" if fmt_number(value, 2) != "—" else "—"


def fmt_hours(value: float) -> str:
    return f"{fmt_number(value, 2)} h" if fmt_number(value, 2) != "—" else "—"


def metric_grid(items: list[tuple[str, str, str | None]], columns: int = 4) -> None:
    cols = st.columns(columns)
    for idx, (label, value, delta) in enumerate(items):
        with cols[idx % columns]:
            st.metric(label, value, delta=delta)


def dataclass_to_frame(obj: Any) -> pd.DataFrame:
    if is_dataclass(obj):
        data = asdict(obj)
    else:
        data = dict(obj)
    return pd.DataFrame(
        [{"metric": key, "value": value} for key, value in data.items()]
    )
