import math
from collections.abc import Sequence

import numpy as np
import pandas as pd
import pulp
from pydantic import Field
from pydantic.dataclasses import dataclass

TOL = 1e-6


@dataclass(frozen=True)
class BatteryParams:
    """
    Attributes:
    power_mw (float): Maksymalna moc ładowania i rozładowania [MW].
    capacity_mwh (float): Całkowita pojemność energetyczna baterii [MWh].
    eta_charge (float): Sprawność procesu ładowania (wartość od 0.0 do 1.0).
    eta_discharge (float): Sprawność procesu rozładowania (wartość od 0.0 do 1.0).
    soc_init_mwh (float): Początkowy stan naładowania (State of Charge) [MWh].
    soc_end_min_mwh (float): Minimalny dopuszczalny stan naładowania na koniec symulacji [MWh].
    """

    power_mw: float = Field(gt=0)
    capacity_mwh: float = Field(gt=0)
    soc_init_mwh: float = Field(default=0.0)
    soc_end_min_mwh: float = Field(default=0.0)
    eta_charge: float = Field(default=1.0, gt=0.0, le=1.0)
    eta_discharge: float = Field(default=1.0, gt=0.0, le=1.0)

    def __post_init__(self):
        if self.soc_init_mwh > self.capacity_mwh:
            raise ValueError(
                f"soc_init_mwh (podane {self.soc_init_mwh} powinno być mniejsze/równe capacity_mwh (podane {self.capacity_mwh}))"
            )

    @property
    def duration_h(self) -> float:
        return self.capacity_mwh / self.power_mw

    @property
    def eta_roundtrip(self) -> float:
        return self.eta_charge * self.eta_discharge

    @classmethod
    def from_roundtrip(
        cls,
        power_mw: float,
        duration_h: float,
        eta_roundtrip: float,
        soc_init_mwh: float = 0.0,
        soc_end_min_mwh: float = 0.0,
    ) -> "BatteryParams":
        capacity = power_mw * duration_h
        eta_single = math.sqrt(eta_roundtrip)

        return cls(
            power_mw=power_mw,
            capacity_mwh=capacity,
            eta_charge=eta_single,
            eta_discharge=eta_single,
            soc_init_mwh=soc_init_mwh,
            soc_end_min_mwh=soc_end_min_mwh,
        )


def _clean_val(v: float | None, tolerancy: float) -> float:
    val = 0.0 if v is None else float(v)
    return 0.0 if abs(val) < tolerancy else val


def optimize_day(
    prices: Sequence[float] | pd.Series, params: BatteryParams, forbid_simultaneous: bool = True
) -> pd.DataFrame:
    n = len(prices)
    if n == 0:
        raise ValueError("Wektor cen nie może być pusty!")

    prices_list = prices.to_list() if isinstance(prices, pd.Series) else list(prices)

    problem = pulp.LpProblem("Magazyn", pulp.LpMaximize)

    charge = {t: problem.add_variable(f"charge_{t}", 0, params.power_mw) for t in range(n)}
    discharge = {t: problem.add_variable(f"discharge_{t}", 0, params.power_mw) for t in range(n)}
    soc = {t: problem.add_variable(f"soc_{t}", 0, params.capacity_mwh) for t in range(n)}

    if forbid_simultaneous:
        is_charging = {t: problem.add_variable(f"is_charging_{t}", cat="Binary") for t in range(n)}

        for t in range(n):
            problem += charge[t] <= params.power_mw * is_charging[t]
            problem += discharge[t] <= params.power_mw * (1 - is_charging[t])

    problem += pulp.lpSum((discharge[t] - charge[t]) * prices_list[t] for t in range(n))

    for t in range(n):
        energy_in = charge[t] * params.eta_charge
        energy_out = discharge[t] / params.eta_discharge

        if t == 0:
            problem += soc[t] == params.soc_init_mwh + energy_in - energy_out
        else:
            problem += soc[t] == soc[t - 1] + energy_in - energy_out

    problem += soc[n - 1] >= params.soc_end_min_mwh

    solver = _make_solver()

    stats = problem.solve(solver)
    solve_status = stats.status

    if solve_status != pulp.LpSolveStatus.Optimal:
        raise RuntimeError(f"Rozwiązanie nieoptymalne: {solve_status.name}")

    index = prices.index if isinstance(prices, pd.Series) else range(n)

    return pd.DataFrame(
        {
            "price": prices_list,
            "charge_mw": [_clean_val(charge[t].value(), TOL) for t in range(n)],
            "discharge_mw": [_clean_val(discharge[t].value(), TOL) for t in range(n)],
            "soc_mwh": [_clean_val(soc[t].value(), TOL) for t in range(n)],
        },
        index=index,
    )


def validate_schedule(
    schedule: pd.DataFrame, params: BatteryParams, tol: float = 1e-6
) -> dict[str, bool]:
    power_charge_ok = schedule["charge_mw"].between(-tol, params.power_mw + tol).all()
    power_discharge_ok = schedule["discharge_mw"].between(-tol, params.power_mw + tol).all()
    power_ok = bool(power_charge_ok and power_discharge_ok)

    soc_bounds_ok = bool(schedule["soc_mwh"].between(-tol, params.capacity_mwh + tol).all())

    energy_delta = (params.eta_charge * schedule["charge_mw"]) - (
        schedule["discharge_mw"] / params.eta_discharge
    )
    expected_soc = params.soc_init_mwh + energy_delta.cumsum()
    energy_balance_ok = bool(np.isclose(expected_soc, schedule["soc_mwh"], atol=tol).all())

    simultaneous_mask = (schedule["charge_mw"] > tol) & (schedule["discharge_mw"] > tol)
    no_simultaneous_ok = bool((~simultaneous_mask).all())

    soc_end_ok = bool(schedule["soc_mwh"].iloc[-1] >= (params.soc_end_min_mwh - tol))

    return {
        "power_ok": power_ok,
        "soc_bounds_ok": soc_bounds_ok,
        "energy_balance_ok": energy_balance_ok,
        "no_simultaneous_ok": no_simultaneous_ok,
        "soc_end_ok": soc_end_ok,
    }


def _make_solver():
    solver_list = pulp.listSolvers(onlyAvailable=True)

    if "HiGHS" in solver_list:
        return pulp.HiGHS(msg=False)
    elif "COIN_CMD" in solver_list:
        return pulp.COIN_CMD(msg=False)
    else:
        raise RuntimeError(f"Brak solvera HiGHS oraz COIN_CMD. Dostępne: {solver_list}")
