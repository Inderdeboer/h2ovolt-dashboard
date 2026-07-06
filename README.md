# H2OVolt Dashboard Demo

Simple Streamlit demo dashboard for viewing EMS data with peak-shaving and load-balancing calculations.

## Run locally

```powershell
python -m streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Put these files in a GitHub repository.
2. Deploy the repository on Streamlit Community Cloud.
3. Set the main file path to `app.py`.

Streamlit will install Python packages from `requirements.txt`.

## Data

The app defaults to the local `data/` folder in this repository:

```text
data/
├─ ElpressEMSData.xlsx
└─ IntelectricEMSData.xlsx
```

Battery names are derived from filenames:

```text
ElpressEMSData.xlsx -> Elpress
IntelectricEMSData.xlsx -> Intelectric
```

You can also paste another folder path locally, or upload a single EMS Excel file in the sidebar.

## Required columns

Each EMS file must contain at least:

- `Timestamp`
- `BatteryVoltage`
- `BatteryCurrent`
- `Load_Power`

Optional columns used when available:

- `PV_Power`
- `Soc`
- `SOCMinLoadProfile`
- `AcOutPowerL1`
- `AcOutPowerL2`
- `AcOutPowerL3`
- `DesiredPeakPowerKw`

## Sign convention

- `Load_Power` is measured grid power at the PCC.
- Positive grid power means import from the grid.
- Negative grid power means export to the grid.
- Negative `Battery_kW` means battery discharge.
- For parallel batteries, useful support subtracts battery standby / auxiliary power.
- For series batteries, useful support uses raw discharge directly.
