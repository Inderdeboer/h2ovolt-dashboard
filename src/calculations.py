from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CalculationOptions:
    battery_power_enabled: bool = True
    flip_battery_sign: bool = False
    battery_connection: str = "parallel"


@dataclass(frozen=True)
class PeakShavingSummary:
    desired_peak_power_kw: float
    peak_with_kw: float
    peak_without_kw: float
    avoided_peak_kw: float
    max_exceed_with_kw: float
    max_exceed_without_kw: float
    avoided_exceed_kw: float
    time_above_with_h: float
    time_above_without_h: float
    total_raw_discharge_kwh: float
    total_standby_kwh: float
    total_support_kwh: float
    total_saved_kwh: float


@dataclass(frozen=True)
class LoadBalancingSummary:
    total_import_with_kwh: float
    total_import_without_kwh: float
    total_export_with_kwh: float
    total_pv_generated_kwh: float
    total_pv_to_battery_kwh: float
    import_saved_kwh: float
    total_battery_standby_kwh: float
    total_useful_battery_support_kwh: float


def smooth(series: pd.Series, window: int) -> pd.Series:
    window = max(1, int(window))
    return series.rolling(window=window, center=True, min_periods=1).mean()


def add_core_calculations(df: pd.DataFrame, options: CalculationOptions) -> pd.DataFrame:
    """
    Recreate the shared power calculations from the original peak shaving and load balancing scripts.

    Sign convention:
    - Load_Power is measured grid power at PCC.
    - positive Load_Power/Grid_kW = grid import.
    - negative Battery_kW = discharge.
    """
    df = df.copy()

    for col in ["AcOutPowerL1", "AcOutPowerL2", "AcOutPowerL3"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)

    if "PV_Power" not in df.columns:
        df["PV_Power"] = 0.0
    df["PV_Power"] = df["PV_Power"].fillna(0.0)

    if "Soc" not in df.columns:
        df["Soc"] = float("nan")

    if "SOCMinLoadProfile" not in df.columns:
        df["SOCMinLoadProfile"] = float("nan")
    df["SOCMinLoadProfile"] = df["SOCMinLoadProfile"].ffill().bfill()

    if "DesiredPeakPowerKw" not in df.columns:
        df["DesiredPeakPowerKw"] = float("nan")
    df["DesiredPeakPower_kW"] = df["DesiredPeakPowerKw"].ffill().bfill()
    df.loc[df["DesiredPeakPowerKw"] == 0, "DesiredPeakPower_kW"] = float("nan")
    df.loc[df["DesiredPeakPower_kW"] <= 0, "DesiredPeakPower_kW"] = float("nan")

    df["Grid_kW"] = df["Load_Power"] / 1000.0
    df["PV_kW"] = df["PV_Power"] / 1000.0
    df["Battery_kW_raw"] = df["BatteryVoltage"] * df["BatteryCurrent"] / 1000.0

    if not options.battery_power_enabled:
        df["Battery_kW"] = 0.0
    elif options.flip_battery_sign:
        df["Battery_kW"] = -df["Battery_kW_raw"]
    else:
        df["Battery_kW"] = df["Battery_kW_raw"]

    df["Battery_standby_kW"] = (
        df["AcOutPowerL1"] + df["AcOutPowerL2"] + df["AcOutPowerL3"]
    ) / 1000.0

    df["Battery_discharge_raw_kW"] = (-df["Battery_kW"]).clip(lower=0)
    df["Battery_charge_raw_kW"] = df["Battery_kW"].clip(lower=0)
    df["PV_to_battery_kW"] = pd.concat(
        [df["PV_kW"].clip(lower=0), df["Battery_charge_raw_kW"]],
        axis=1,
    ).min(axis=1)
    if options.battery_connection == "series":
        df["Battery_support_kW"] = df["Battery_discharge_raw_kW"]
        df["Battery_standby_compensated_kW"] = 0.0
    else:
        df["Battery_support_kW"] = (
            df["Battery_discharge_raw_kW"] - df["Battery_standby_kW"]
        ).clip(lower=0)
        df["Battery_standby_compensated_kW"] = df["Battery_standby_kW"]

    df["Grid_without_battery_kW"] = df["Grid_kW"] + df["Battery_support_kW"]
    df["Import_with_battery_kW"] = df["Grid_kW"].clip(lower=0)
    df["Export_with_battery_kW"] = (-df["Grid_kW"]).clip(lower=0)
    df["Import_without_battery_kW"] = df["Grid_without_battery_kW"].clip(lower=0)

    df["dt_h"] = df["Timestamp"].diff().dt.total_seconds() / 3600.0
    median_dt = df["dt_h"].median()
    if pd.isna(median_dt):
        median_dt = 0.0
    df["dt_h"] = df["dt_h"].fillna(median_dt).fillna(0.0)

    df["Battery_support_kWh"] = df["Battery_support_kW"] * df["dt_h"]
    df["Battery_discharge_raw_kWh"] = df["Battery_discharge_raw_kW"] * df["dt_h"]
    df["Battery_charge_raw_kWh"] = df["Battery_charge_raw_kW"] * df["dt_h"]
    df["Battery_standby_kWh"] = df["Battery_standby_kW"] * df["dt_h"]
    df["Battery_standby_compensated_kWh"] = df["Battery_standby_compensated_kW"] * df["dt_h"]
    df["PV_generated_kWh"] = df["PV_kW"].clip(lower=0) * df["dt_h"]
    df["PV_to_battery_kWh"] = df["PV_to_battery_kW"] * df["dt_h"]
    df["Export_with_battery_kWh"] = df["Export_with_battery_kW"] * df["dt_h"]
    df["Import_saved_kWh"] = (
        (df["Import_without_battery_kW"] - df["Import_with_battery_kW"]) * df["dt_h"]
    ).clip(lower=0)

    return add_peak_shaving_columns(df)


def add_peak_shaving_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add 15-minute rolling average and exceedance columns from the peak shaving script."""
    df = df.copy()
    df_ts = df.set_index("Timestamp")

    df["Import_with_battery_15min_avg_kW"] = (
        df_ts["Import_with_battery_kW"].rolling("15min", min_periods=1).mean().values
    )
    df["Import_without_battery_15min_avg_kW"] = (
        df_ts["Import_without_battery_kW"].rolling("15min", min_periods=1).mean().values
    )

    df["Exceed_with_15min_kW"] = (
        df["Import_with_battery_15min_avg_kW"] - df["DesiredPeakPower_kW"]
    ).clip(lower=0)
    df["Exceed_without_15min_kW"] = (
        df["Import_without_battery_15min_avg_kW"] - df["DesiredPeakPower_kW"]
    ).clip(lower=0)

    return df


def summarize_peak_shaving(df: pd.DataFrame) -> PeakShavingSummary:
    if df.empty:
        nan = float("nan")
        return PeakShavingSummary(nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan)

    peak_with = df["Import_with_battery_15min_avg_kW"].max()
    peak_without = df["Import_without_battery_15min_avg_kW"].max()
    max_exceed_with = df["Exceed_with_15min_kW"].max()
    max_exceed_without = df["Exceed_without_15min_kW"].max()

    if df["DesiredPeakPower_kW"].notna().any():
        desired_peak_power = df["DesiredPeakPower_kW"].dropna().iloc[-1]
    else:
        desired_peak_power = float("nan")

    return PeakShavingSummary(
        desired_peak_power_kw=float(desired_peak_power),
        peak_with_kw=float(peak_with),
        peak_without_kw=float(peak_without),
        avoided_peak_kw=float(peak_without - peak_with),
        max_exceed_with_kw=float(max_exceed_with),
        max_exceed_without_kw=float(max_exceed_without),
        avoided_exceed_kw=float(max_exceed_without - max_exceed_with),
        time_above_with_h=float(((df["Exceed_with_15min_kW"] > 0).astype(int) * df["dt_h"]).sum()),
        time_above_without_h=float(((df["Exceed_without_15min_kW"] > 0).astype(int) * df["dt_h"]).sum()),
        total_raw_discharge_kwh=float(df["Battery_discharge_raw_kWh"].sum()),
        total_standby_kwh=float(df["Battery_standby_compensated_kWh"].sum()),
        total_support_kwh=float(df["Battery_support_kWh"].sum()),
        total_saved_kwh=float(df["Import_saved_kWh"].sum()),
    )


def summarize_load_balancing(df: pd.DataFrame) -> LoadBalancingSummary:
    return LoadBalancingSummary(
        total_import_with_kwh=float((df["Import_with_battery_kW"] * df["dt_h"]).sum()),
        total_import_without_kwh=float((df["Import_without_battery_kW"] * df["dt_h"]).sum()),
        total_export_with_kwh=float(df["Export_with_battery_kWh"].sum()),
        total_pv_generated_kwh=float(df["PV_generated_kWh"].sum()),
        total_pv_to_battery_kwh=float(df["PV_to_battery_kWh"].sum()),
        import_saved_kwh=float(df["Import_saved_kWh"].sum()),
        total_battery_standby_kwh=float(df["Battery_standby_compensated_kWh"].sum()),
        total_useful_battery_support_kwh=float(df["Battery_support_kWh"].sum()),
    )


def filter_timeframe(
    df: pd.DataFrame,
    *,
    mode: str,
    single_day,
    start_date,
    end_date,
    last_days: int,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    timestamps = df["Timestamp"]

    if mode == "Single day":
        day_start = pd.Timestamp(single_day).normalize()
        day_end = day_start + pd.Timedelta(days=1)
        return df[(timestamps >= day_start) & (timestamps < day_end)].copy()

    if mode == "Date range":
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)
        return df[(timestamps >= start_ts) & (timestamps < end_ts)].copy()

    if mode == "Last N days":
        end_ts = timestamps.max()
        start_ts = end_ts - pd.Timedelta(days=int(last_days))
        return df[timestamps >= start_ts].copy()

    return df.copy()
