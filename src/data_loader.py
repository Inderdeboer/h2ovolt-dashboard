from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import streamlit as st


class DataValidationError(ValueError):
    """Raised when a file misses required EMS data columns."""


def parse_number(series: pd.Series) -> pd.Series:
    """Parse numbers that may use comma decimals, matching the original scripts."""
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )


def battery_name_from_excel(path: str | Path) -> str:
    """Turn filenames like ElpressEMSData.xlsx into Elpress."""
    stem = Path(path).stem
    for suffix in ("EMSData", "EmsData", "emsdata"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)] or stem
    return re.sub(r"[_\- ]*EMS[_\- ]*Data$", "", stem, flags=re.IGNORECASE) or stem


@st.cache_data(show_spinner=False)
def find_excel_files(folder_string: str) -> list[dict[str, str]]:
    """List possible EMS Excel files without opening/loading their contents."""
    folder = Path(folder_string).expanduser()
    if not folder.exists():
        return []
    if not folder.is_dir():
        return []

    files: list[Path] = []
    for pattern in ("*EMSData.xlsx", "*EMSData.xls", "*.xlsx", "*.xls"):
        files.extend(folder.glob(pattern))

    unique_files = sorted({p.resolve() for p in files if p.is_file() and not p.name.startswith("~$")})
    return [
        {
            "name": battery_name_from_excel(path),
            "filename": path.name,
            "path": str(path),
            "modified_ns": str(path.stat().st_mtime_ns),
        }
        for path in unique_files
    ]


@st.cache_data(show_spinner=False)
def read_excel_path(path_string: str, modified_ns: int | str) -> pd.DataFrame:
    """Read one selected Excel file from disk. modified_ns is used to invalidate cache."""
    _ = modified_ns
    return pd.read_excel(path_string, engine="openpyxl" if path_string.lower().endswith(".xlsx") else None)


@st.cache_data(show_spinner=False)
def read_excel_bytes(file_bytes: bytes) -> pd.DataFrame:
    """Read an uploaded Excel file."""
    return pd.read_excel(BytesIO(file_bytes))


def load_raw_excel_from_path(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(
            "Excel file was not found. Check the folder path or file name.\n\n"
            f"Missing file: {path}"
        )
    return read_excel_path(str(path), path.stat().st_mtime_ns)


def load_raw_excel_from_upload(file_bytes: bytes) -> pd.DataFrame:
    return read_excel_bytes(file_bytes)


def clean_ems_dataframe(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | list[str]]]:
    """
    Basic cleaning shared by peak shaving and load balancing.

    This does not perform battery calculations; see src/calculations.py.
    """
    required_columns = ["Timestamp", "BatteryVoltage", "BatteryCurrent", "Load_Power"]
    missing = [column for column in required_columns if column not in raw_df.columns]
    if missing:
        raise DataValidationError("Missing required column(s): " + ", ".join(missing))

    df = raw_df.copy()
    initial_rows = len(df)

    df = df.dropna(subset=["Timestamp"]).copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Timestamp"]).copy()
    df = df.sort_values("Timestamp").reset_index(drop=True)

    numeric_cols = [
        "BatteryVoltage",
        "BatteryCurrent",
        "PV_Power",
        "Load_Power",
        "Soc",
        "SOCMinLoadProfile",
        "AcOutPowerL1",
        "AcOutPowerL2",
        "AcOutPowerL3",
        "DesiredPeakPowerKw",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = parse_number(df[col])

    before_required_drop = len(df)
    df = df.dropna(subset=["BatteryVoltage", "BatteryCurrent", "Load_Power"]).copy()

    info: dict[str, int | list[str]] = {
        "initial_rows": initial_rows,
        "rows_after_timestamp_cleaning": before_required_drop,
        "rows_after_required_power_cleaning": len(df),
        "available_columns": list(raw_df.columns),
    }
    return df, info
