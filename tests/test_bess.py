import datetime
import math

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.ml.bess.battery import BatteryParams, _clean_val, optimize_day, validate_schedule
from src.ml.bess.prices import prepare_price_data
from src.ml.bess.settlement import settle_schedule
from src.ml.bess.strategies import (
    BessStrategy,
    DayResult,
    naive_schedule,
    naive_strategy,
    run_day_strategies,
)

# ---------------------------------------------------------------------------
# 1. Testy BatteryParams i funkcji pomocniczych
# ---------------------------------------------------------------------------


def test_battery_params_properties_and_from_roundtrip():
    """Weryfikuje wyliczanie duration_h, eta_roundtrip oraz konstruktor from_roundtrip."""
    params = BatteryParams.from_roundtrip(
        power_mw=2.0,
        duration_h=4.0,
        eta_roundtrip=0.81,
        soc_init_mwh=1.0,
        soc_end_min_mwh=0.5,
    )
    assert params.capacity_mwh == pytest.approx(8.0)
    assert params.duration_h == pytest.approx(4.0)
    assert params.eta_charge == pytest.approx(0.9)
    assert params.eta_discharge == pytest.approx(0.9)
    assert params.eta_roundtrip == pytest.approx(0.81)
    assert params.soc_init_mwh == 1.0
    assert params.soc_end_min_mwh == 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"power_mw": 0.0, "capacity_mwh": 2.0},
        {"power_mw": -1.0, "capacity_mwh": 2.0},
        {"power_mw": 1.0, "capacity_mwh": 0.0},
        {"power_mw": 1.0, "capacity_mwh": 2.0, "eta_charge": 0.0},
        {"power_mw": 1.0, "capacity_mwh": 2.0, "eta_charge": 1.1},
        {"power_mw": 1.0, "capacity_mwh": 2.0, "eta_discharge": -0.5},
    ],
)
def test_battery_params_invalid_fields_raise(kwargs):
    """Niepoprawne wartości fizyczne baterii muszą rzucić ValidationError."""
    with pytest.raises(ValidationError):
        BatteryParams(**kwargs)


def test_battery_params_soc_init_greater_than_capacity_raises():
    """soc_init_mwh większy niż capacity_mwh musi rzucić ValueError."""
    with pytest.raises(ValueError, match="soc_init_mwh"):
        BatteryParams(power_mw=1.0, capacity_mwh=2.0, soc_init_mwh=2.5)


def test_clean_val():
    """Weryfikuje czyszczenie wartości bliskich zeru i None."""
    assert _clean_val(None, 1e-6) == 0.0
    assert _clean_val(1e-9, 1e-6) == 0.0
    assert _clean_val(-1e-9, 1e-6) == 0.0
    assert _clean_val(1.5, 1e-6) == 1.5


# ---------------------------------------------------------------------------
# 2. Testy optymalizacji MILP (optimize_day) i walidacji (validate_schedule)
# ---------------------------------------------------------------------------


def test_optimize_day_4h():
    """Smoke test: weryfikuje rozwiązanie MILP na prostym 4-godzinnym profilu cen."""
    params = BatteryParams(
        power_mw=1.0,
        capacity_mwh=2.0,
        soc_init_mwh=0.0,
        soc_end_min_mwh=0.0,
        eta_charge=1.0,
        eta_discharge=1.0,
    )
    prices = [50.0, 100.0, 500.0, 450.0]
    schedule = optimize_day(prices, params)

    assert isinstance(schedule, pd.DataFrame)
    assert len(schedule) == 4
    assert set(schedule.columns) == {"price", "charge_mw", "discharge_mw", "soc_mwh"}

    validation = validate_schedule(schedule, params)
    assert all(validation.values()), f"Walidacja harmonogramu nie przeszła: {validation}"

    # Ładowanie w pierwszych 2 najtańszych godzinach (po 1 MW -> pełny magazyn 2 MWh)
    assert schedule["charge_mw"].iloc[0] == pytest.approx(1.0)
    assert schedule["charge_mw"].iloc[1] == pytest.approx(1.0)
    # Rozładowanie w 2 najdroższych godzinach
    assert schedule["discharge_mw"].iloc[2] == pytest.approx(1.0)
    assert schedule["discharge_mw"].iloc[3] == pytest.approx(1.0)


def test_optimize_day_empty_prices_raises():
    """Pusty wektor cen musi rzucić ValueError."""
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0)
    with pytest.raises(ValueError, match="pusty"):
        optimize_day([], params)


def test_optimize_day_respects_soc_end_min_and_efficiency():
    """Weryfikuje zachowanie wymaganego SoC końcowego oraz sprawności < 100%."""
    params = BatteryParams(
        power_mw=2.0,
        capacity_mwh=4.0,
        soc_init_mwh=1.0,
        soc_end_min_mwh=2.0,
        eta_charge=0.9,
        eta_discharge=0.9,
    )
    prices = [100.0, 80.0, 600.0, 50.0]
    schedule = optimize_day(prices, params, forbid_simultaneous=True)

    validation = validate_schedule(schedule, params)
    assert all(validation.values()), f"Nieudana walidacja: {validation}"
    assert schedule["soc_mwh"].iloc[-1] >= params.soc_end_min_mwh - 1e-5


def test_validate_schedule_detects_violations():
    """Sprawdza, czy validate_schedule poprawnie wykrywa naruszenia fizyczne."""
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0, soc_init_mwh=0.0, soc_end_min_mwh=1.0)
    bad_schedule = pd.DataFrame(
        {
            "price": [100.0, 200.0],
            "charge_mw": [1.5, 0.5],  # przekroczona moc 1.0 MW i jednoczesna praca w t=1
            "discharge_mw": [0.0, 0.5],
            "soc_mwh": [2.5, 0.2],  # przekroczona pojemność 2.0 MWh i za niski soc końcowy
        }
    )
    res = validate_schedule(bad_schedule, params)
    assert res["power_ok"] is False
    assert res["soc_bounds_ok"] is False
    assert res["no_simultaneous_ok"] is False
    assert res["soc_end_ok"] is False


# ---------------------------------------------------------------------------
# 3. Testy rozliczeń finansowych (settle_schedule) i przygotowania cen
# ---------------------------------------------------------------------------


def test_settle_schedule():
    """Smoke test: weryfikuje poprawność finansowego rozliczenia wykonanego harmonogramu."""
    schedule = pd.DataFrame(
        {
            "charge_mw": [1.0, 0.0],
            "discharge_mw": [0.0, 1.0],
        }
    )
    prices_real = [100.0, 300.0]

    pnl = settle_schedule(schedule, prices_real, dt_h=1.0)
    assert pnl == pytest.approx(200.0, abs=1e-5)

    # Test z pd.Series i dt_h = 0.25 (kwadrans)
    pnl_quarter = settle_schedule(schedule, pd.Series(prices_real), dt_h=0.25)
    assert pnl_quarter == pytest.approx(50.0, abs=1e-5)


def test_settle_schedule_length_mismatch():
    """Weryfikuje zgłoszenie błędu przy rozbieżności długości wektorów."""
    schedule = pd.DataFrame({"charge_mw": [1.0], "discharge_mw": [0.0]})
    with pytest.raises(ValueError):
        settle_schedule(schedule, [100.0, 200.0])


def test_prepare_price_data():
    """Weryfikuje łączenie cen rzeczywistych i prognozowanych oraz konwersję strefy czasowej."""
    idx_utc = pd.date_range("2026-10-20 00:00", periods=4, freq="h", tz="UTC")
    real_df = pd.DataFrame({"fixing_1_pln_mwh": [300.0, 310.0, 320.0, 330.0]}, index=idx_utc)
    fcst_df = pd.DataFrame({"forecast_pln_mwh": [290.0, 315.0, 325.0, 340.0]}, index=idx_utc)

    merged = prepare_price_data(real_df, fcst_df)

    assert "price_real" in merged.columns  # ignore
    assert "price_forecast" in merged.columns
    assert str(merged.index.tz) == "Europe/Warsaw"
    assert len(merged) == 4


# ---------------------------------------------------------------------------
# 4. Testy strategii (BessStrategy, naive_schedule, run_day_strategies)
# ---------------------------------------------------------------------------


def test_bess_strategy_enum():
    """Weryfikuje wartości wyliczeniowe BessStrategy."""
    assert BessStrategy.PERFECT_FORESIGHT == "perfect_foresight"
    assert BessStrategy.FORECAST_BASED == "forecast_based"
    assert BessStrategy.NAIVE == "naive"


def test_naive_schedule_and_strategy():
    """Weryfikuje działanie strategii naiwnej na pełnej dobie."""
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0, eta_charge=1.0, eta_discharge=1.0)
    prev_prices = pd.Series([100.0] * 6 + [50.0] * 6 + [200.0] * 6 + [600.0] * 6)

    sched = naive_schedule(prev_prices, params)
    assert len(sched) == 24
    validation = validate_schedule(sched, params)
    assert all(validation.values())

    # Walidacja błędu przy różnej liczbie godzin
    day_df = pd.DataFrame({"price_real": [100.0] * 24})
    prev_short = pd.DataFrame({"price_real": [100.0] * 23})
    with pytest.raises(ValueError, match="Liczba godzin"):
        naive_strategy(day_df, prev_short, params, price_col="price_real")


def test_run_day_strategies_full_data():
    """Weryfikuje uruchomienie wszystkich 3 strategii dla dnia z cenami rzeczywistymi i dobą poprzednią."""
    idx = pd.date_range("2026-10-19 00:00", periods=48, freq="h", tz="Europe/Warsaw")
    hourly_pattern = [200.0 + 150.0 * math.sin(2 * math.pi * (h - 6) / 24) for h in range(24)]
    prices = pd.DataFrame(
        {
            "price_real": hourly_pattern * 2,
            "price_forecast": [p + 10.0 for p in hourly_pattern] * 2,
        },
        index=idx,
    )
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0, eta_charge=0.95, eta_discharge=0.95)
    target_day = datetime.date(2026, 10, 20)

    res: DayResult = run_day_strategies(prices, target_day, params)

    assert res.revenue_basis == "real"
    assert set(res.schedules.keys()) == {
        BessStrategy.FORECAST_BASED,
        BessStrategy.PERFECT_FORESIGHT,
        BessStrategy.NAIVE,
    }
    assert not res.summary.empty
    assert res.summary.loc[BessStrategy.PERFECT_FORESIGHT, "capture_rate"] == pytest.approx(1.0)
    assert res.summary.loc[BessStrategy.FORECAST_BASED, "revenue_pln"] <= (
        res.summary.loc[BessStrategy.PERFECT_FORESIGHT, "revenue_pln"] + 1e-4
    )


def test_run_day_strategies_forecast_only_without_real_prices():
    """Gdy brak cen rzeczywistych (np. doba jutrzejsza), działa tylko forecast_based rozliczany po prognozie."""
    idx = pd.date_range("2026-10-21 00:00", periods=24, freq="h", tz="Europe/Warsaw")
    prices = pd.DataFrame(
        {
            "price_real": [np.nan] * 24,
            "price_forecast": [100.0] * 12 + [400.0] * 12,
        },
        index=idx,
    )
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0)
    res = run_day_strategies(prices, datetime.date(2026, 10, 21), params)

    assert res.revenue_basis == "forecast"
    assert list(res.schedules.keys()) == [BessStrategy.FORECAST_BASED]
    assert any("prognozy cen" in note for note in res.notes)


def test_run_day_strategies_missing_forecast_returns_empty():
    """Gdy brak prognoz cen dla wybranego dnia, funkcja bezpiecznie zwraca pusty DayResult z notatką."""
    idx = pd.date_range("2026-10-21 00:00", periods=24, freq="h", tz="Europe/Warsaw")
    prices = pd.DataFrame({"price_real": [200.0] * 24, "price_forecast": [np.nan] * 24}, index=idx)
    params = BatteryParams(power_mw=1.0, capacity_mwh=2.0)

    res = run_day_strategies(prices, datetime.date(2026, 10, 21), params)
    assert res.schedules == {}
    assert res.summary.empty
    assert any("Brak kompletnej prognozy" in n for n in res.notes)
