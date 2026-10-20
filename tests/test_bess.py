import pandas as pd
import pytest

from src.ml.bess.battery import BatteryParams, optimize_day, validate_schedule
from src.ml.bess.settlement import settle_schedule


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

    assert schedule["charge_mw"].iloc[0] > 0.0
    assert schedule["discharge_mw"].iloc[2] > 0.0


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


def test_settle_schedule_length_mismatch():
    """Weryfikuje zgłoszenie błędu przy rozbieżności długości wektorów."""
    schedule = pd.DataFrame({"charge_mw": [1.0], "discharge_mw": [0.0]})
    with pytest.raises(ValueError):
        settle_schedule(schedule, [100.0, 200.0])
