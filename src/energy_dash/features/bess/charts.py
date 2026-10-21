from typing import Literal

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_strategy_schedule(
    df: pd.DataFrame,
    prices_df: pd.DataFrame,
    revenue: float,
    revenue_basis: Literal["real", "forecast"],
    strategy_name: str = "",
) -> go.Figure:
    """
    Rysuje wykres cen energii oraz harmonogram pracy magazynu (ładowanie, rozładowanie, SoC).
    """
    price_label = "Ceny energii [PLN/MWh]"
    basis_label = "wg cen realnych" if revenue_basis == "real" else "wg prognozy"

    title_prefix = f"{strategy_name} - " if strategy_name else ""
    schedule_title = f"{title_prefix}Przychód ({basis_label}): {revenue:,.2f} PLN"

    # Tworzymy 2 wiersze: góra (ceny), dół (moc + SoC na prawej osi Y)
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.35, 0.65],
        subplot_titles=(price_label, schedule_title),
        specs=[
            [{"secondary_y": False}],
            [{"secondary_y": True}],
        ],
    )

    # --- Wiersz 1: Cena ---
    if "price_real" in prices_df.columns and not prices_df["price_real"].isna().all():
        fig.add_trace(
            go.Scatter(
                x=prices_df.index,
                y=prices_df["price_real"],
                mode="lines+markers",
                name="Cena rzeczywista (Fixing I)",
                line=dict(color="#1f77b4", width=2),
            ),
            row=1,
            col=1,
        )

    if "price_forecast" in prices_df.columns:
        fig.add_trace(
            go.Scatter(
                x=prices_df.index,
                y=prices_df["price_forecast"],
                mode="lines+markers",
                name="Prognoza ceny",
                line=dict(color="#ff7f0e", width=2, dash="dot"),
            ),
            row=1,
            col=1,
        )

    # --- Wiersz 2: Rozładowanie (w górę, czerwone) ---
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["discharge_mw"].round(2),
            name="Rozładowanie",
            marker_color="#d62728",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )

    # --- Wiersz 2: Ładowanie (w dół, zielone) ---
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=-df["charge_mw"].round(2),
            name="Ładowanie",
            marker_color="#2ca02c",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )

    # --- Wiersz 2 (prawa oś Y): Stan naładowania (SoC) ---
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["soc_mwh"].round(2),
            mode="lines",
            name="SoC [MWh]",
            line=dict(color="gray", width=2, dash="dash"),
        ),
        row=2,
        col=1,
        secondary_y=True,
    )

    # --- Ustawienia osi i wyglądu ---
    fig.update_layout(
        height=550,
        barmode="relative",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="right",
            x=1,
        ),
        margin=dict(l=40, r=40, t=60, b=40),
    )

    fig.update_yaxes(title_text="PLN / MWh", row=1, col=1)
    fig.update_yaxes(title_text="Moc [MW]", row=2, col=1, secondary_y=False)
    fig.update_yaxes(
        title_text="SoC [MWh]",
        row=2,
        col=1,
        secondary_y=True,
        showgrid=False,
    )

    return fig
