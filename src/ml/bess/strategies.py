import datetime
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from src.ml.bess.battery import BatteryParams, optimize_day, validate_schedule
from src.ml.bess.settlement import settle_schedule

PERFECT_FORESIGHT = "perfect_foresight"
FORECAST_BASED = "forecast_based"
NAIVE = "naive"


def perfect_foresight_schedule(
    day_df: pd.DataFrame,
    params: BatteryParams,
    price_col: str = "fixing_1_pln_mwh",
    **kwargs,
) -> pd.DataFrame:
    """
    Tworzy idealny harmonogram (benchmark teoretyczny) bazująac na cenach rzeczywistych
    """
    return optimize_day(prices=day_df[price_col], params=params, **kwargs)


def forecast_schedule(
    day_df: pd.DataFrame, params: BatteryParams, price_col: str = "forecast_pln_mwh", **kwargs
) -> pd.DataFrame:
    """
    Tworzy harmonogram dla prognoz cen
    """
    return optimize_day(prices=day_df[price_col], params=params, **kwargs)


def naive_schedule(prices_prev_day: pd.DataFrame, params: BatteryParams) -> pd.DataFrame:
    """
    Tworzy harmonogram metodą heurystyczną na podstawie cen z doby poprzedniej.

    Wybiera N najdroższych godzin do rozładowania i N najtańszych do ładowania,
    a następnie przeprowadza symulację fizyczną krok po kroku.
    """
    n = len(prices_prev_day)

    if n == 0:
        raise ValueError("Wektor cen nie może być pusty!")

    prices_array = np.asarray(prices_prev_day, dtype=float)

    n_hours = max(1, round(params.duration_h))
    n_hours = min(n_hours, n // 2) if n >= 2 else 0

    sorted_prices_desc = np.argsort(prices_array)[::-1]

    discharge_hours = set(sorted_prices_desc[:n_hours])

    remaining_hors = [idx for idx in sorted_prices_desc if idx not in discharge_hours]

    charge_hours = set(remaining_hors[-n_hours:] if n_hours > 0 else [])

    charge_mw = np.zeros(n, dtype=float)
    discharge_mw = np.zeros(n, dtype=float)
    soc_mwh = np.zeros(n, dtype=float)

    current_soc = params.soc_init_mwh

    for t in range(n):
        if t in charge_hours:
            max_charge_by_capacity = (params.capacity_mwh - current_soc) / params.eta_charge

            ch = min(params.power_mw, max(0.0, max_charge_by_capacity))
            dis = 0.0
        elif t in discharge_hours:
            max_discharge_by_soc = current_soc * params.eta_discharge
            dis = min(params.power_mw, max(0.0, max_discharge_by_soc))
            ch = 0.0
        else:
            ch = 0.0
            dis = 0.0

        current_soc = current_soc + (ch * params.eta_charge) - (dis / params.eta_discharge)

        charge_mw[t] = ch
        discharge_mw[t] = dis
        soc_mwh[t] = current_soc

    return pd.DataFrame(
        {
            "price": prices_array,
            "charge_mw": charge_mw,
            "discharge_mw": discharge_mw,
            "soc_mwh": soc_mwh,
        }
    )


def naive_strategy(
    day_df: pd.DataFrame,
    prev_day_df: pd.DataFrame,
    params: BatteryParams,
    price_col: str = "fixing_1_pln_mwh",
) -> pd.DataFrame:

    if len(day_df) != len(prev_day_df):
        raise ValueError(
            f"Liczba godzin w dobie bieżącej ({len(day_df)}) i poprzedniej ({len(prev_day_df)}) musi być taka sama!"
        )

    sched = naive_schedule(prices_prev_day=prev_day_df[price_col], params=params)

    sched.index = day_df.index
    return sched


@dataclass
class DayResult:
    schedules: dict[str, pd.DataFrame]
    summary: pd.DataFrame
    prices: pd.DataFrame
    revenue_basis: Literal["real", "forecast"]
    notes: list[str]


def run_day_strategies(
    prices: pd.DataFrame,
    day: datetime.date,
    params: BatteryParams,
    forbid_simultaneous: bool = True,
) -> DayResult:

    notes: list[str] = []
    schedules: dict[str, pd.DataFrame] = {}

    prev_mask = prices.index.date == (day - datetime.timedelta(days=1))
    day_mask = prices.index.date == day

    prev_df = prices.loc[prev_mask]
    day_df = prices.loc[day_mask]

    if (
        day_df.empty
        or "price_forecast" not in day_df.columns
        or day_df["price_forecast"].isna().any()
    ):
        return DayResult(
            schedules={},
            summary=pd.DataFrame(columns=["revenue_pln", "n_cycles", "capture_rate"]),
            prices=day_df,
            revenue_basis="forecast",
            notes=["Brak kompletnej prognozy cen dla wybranego dnia."],
        )

    has_real = "price_real" in day_df.columns and not day_df["price_real"].isna().any()
    revenue_basis: Literal["real", "forecast"] = "real" if has_real else "forecast"

    # Forecast-based
    try:
        sched_fcst = forecast_schedule(
            day_df, params, forbid_simultaneous=forbid_simultaneous, price_col="price_forecast"
        )
        schedules[FORECAST_BASED] = sched_fcst
    except RuntimeError as err:
        notes.append(f"Strategia '{FORECAST_BASED}' zgłosiła błąd solvera: {err}")

    # Perfect foresight
    if has_real:
        try:
            sched_pf = perfect_foresight_schedule(
                day_df, params, forbid_simultaneous=forbid_simultaneous, price_col="price_real"
            )
            schedules[PERFECT_FORESIGHT] = sched_pf
        except RuntimeError as err:
            notes.append(f"Strategia '{PERFECT_FORESIGHT}' zgłosiła błąd solvera: {err}")

    # strategia Naive

    if has_real:
        has_prev_real = (
            not prev_df.empty
            and "price_real" in prev_df.columns
            and not prev_df["price_real"].isna().any()
        )

        is_regular_hours = len(day_df) == 24 and len(prev_df) == 24

        if has_prev_real and is_regular_hours:
            try:
                sched_naive = naive_strategy(day_df, prev_df, params, price_col="price_real")
                schedules[NAIVE] = sched_naive
            except RuntimeError as err:
                notes.append(f"Strategia '{NAIVE}' zgłosiła błąd solvera: {err}")
        else:
            notes.append(
                f"Pominięto '{NAIVE}': wymaga dokładnie 24h w dobie bieżącej i poprzedniej oraz cen rzeczywistych."
            )

    for strat_name, sched in schedules.items():
        validation = validate_schedule(sched, params)

        failed_checks = [check_name for check_name, passed in validation.items() if not passed]

        if failed_checks:
            notes.append(
                f"Ostrzeżenie walidacji dla '{strat_name}': "
                f"nieudane testy: {', '.join(failed_checks)}"
            )

    if has_real:
        price_col_for_settlement = "price_real"
    else:
        price_col_for_settlement = "price_forecast"
        notes.append(
            "Brak cen rzeczywistych dla tego dnia. Przychód liczony na podstawie prognozy cen."
        )
    summary_rows = {}

    for strat_name, sched in schedules.items():
        rev = settle_schedule(sched, day_df[price_col_for_settlement])

        discharge_energy = sched["discharge_mw"].sum()
        n_cycles = discharge_energy / params.capacity_mwh

        summary_rows[strat_name] = {
            "revenue_pln": rev,
            "n_cycles": n_cycles,
            "capture_rate": np.nan,
        }

    summary_df = pd.DataFrame.from_dict(summary_rows, orient="index")
    if summary_df.empty:
        summary_df = pd.DataFrame(columns=["revenue_pln", "n_cycles", "capture_rate"])

    if PERFECT_FORESIGHT in summary_df.index:
        pf_revenue = summary_df.loc[PERFECT_FORESIGHT, "revenue_pln"]
        if pf_revenue > 0:
            summary_df["capture_rate"] = summary_df["revenue_pln"] / pf_revenue

    return DayResult(
        schedules=schedules,
        summary=summary_df,
        prices=day_df,
        revenue_basis=revenue_basis,
        notes=notes,
    )
