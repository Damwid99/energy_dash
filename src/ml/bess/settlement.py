from collections.abc import Sequence

import numpy as np
import pandas as pd


def settle_schedule(
    schedule: pd.DataFrame, price_real: Sequence[float] | pd.Series, dt_h: float = 1.0
) -> float:

    if len(schedule) != len(price_real):
        raise ValueError(
            f"Dłuogość schdedule {len(schedule)} musi być taka sama jak długość price_real {len(price_real)}"
        )

    price_real = (
        price_real.to_numpy()
        if isinstance(price_real, pd.Series)
        else np.asarray(price_real, dtype=float)
    )

    settle = (
        (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy()) * price_real * dt_h
    ).sum()

    return float(settle)
