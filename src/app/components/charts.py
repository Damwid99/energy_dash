from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Definicja przedziałów: (dolny_kwantyl, górny_kwantyl, kolor_wypełnienia, nazwa_w_legendzie)
CONFIDENCE_INTERVALS = [
    ("p05", "p95", "rgba(31, 119, 180, 0.10)", "Przedział P05–P95"),
    ("p10", "p90", "rgba(31, 119, 180, 0.15)", "Przedział P10–P90"),
    ("p25", "p75", "rgba(31, 119, 180, 0.25)", "Przedział P25–P75"),
]


def get_background_colors(
    status_series, pos_color="rgba(59, 130, 246, 0.25)", neg_color="rgba(239, 68, 68, 0.25)"
):
    conditions = [status_series > 0, status_series < 0]
    choices = [pos_color, neg_color]
    return np.select(conditions, choices, default="rgba(0,0,0,0)")


def _get_x_axis(df: pd.DataFrame) -> pd.Series | pd.Index:
    """Zwraca oś czasu z kolumny datetime_local/datetime_utc lub z indeksu."""
    for col in ("datetime_local", "datetime_utc"):
        if col in df.columns:
            return df[col]
    return df.index


def _build_price_indices_chart(df: pd.DataFrame, interval_minutes: int, title: str) -> go.Figure:
    """Prywatna funkcja pomocnicza budująca wykres Plotly dla zadanego interwału.

    Wykorzystuje czysto wektorowe przekształcenia oraz bezpieczną obsługę brakujących wartości.
    """
    fig = go.Figure()
    x_axis = _get_x_axis(df)

    status = df["kse_contracting_status"].fillna(0)
    y_bar = np.where(status != 0, 1, np.nan)

    bar_width_ms = interval_minutes * 60 * 1000

    # --- 1. SERIA SŁUPKOWA (TŁO) ---
    fig.add_trace(
        go.Bar(
            x=x_axis,
            y=y_bar,
            yaxis="y2",
            marker_color=get_background_colors(df["kse_contracting_status"]),
            marker_line_width=0,
            width=bar_width_ms,
            name="Stan zakontraktowania",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # --- 2. PRZEDZIAŁY UFNOŚCI (OPCJONALNE) ---
    for low_col, high_col, fill_color, label in CONFIDENCE_INTERVALS:
        if {low_col, high_col}.issubset(df.columns) and df[low_col].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=x_axis,
                    y=df[low_col],
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                    legendgroup=label,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=x_axis,
                    y=df[high_col],
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor=fill_color,
                    name=label,
                    hoverinfo="skip",
                    legendgroup=label,
                )
            )

    # --- 3. PROGNOZA FIXING I ---
    if "fixing_1_forecast_pln_mwh" in df.columns and df["fixing_1_forecast_pln_mwh"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=x_axis,
                y=df["fixing_1_forecast_pln_mwh"],
                mode="lines",
                name="Fixing I (Prognoza)",
                line=dict(color="#1f77b4", dash="dash"),
            )
        )

    # --- 4. SERIE LINIOWE (INDEKSY CENOWE) ---
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=df["fixing_1_pln_mwh"],
            mode="lines",
            name="Fixing I",
            line=dict(color="#1f77b4"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=df["fixing_2_pln_mwh"],
            mode="lines",
            name="Fixing II",
            line=dict(color="#ff7f0e"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_axis,
            y=df["cen_pln_mwh"],
            mode="lines",
            name="CEN",
            line=dict(color="#2ca02c"),
        )
    )

    fig.update_layout(
        title=title,
        xaxis=dict(title="Czas", type="date"),
        yaxis=dict(title="Cena [PLN/MWh]", domain=[0, 1]),
        yaxis2=dict(
            overlaying="y",
            range=[0, 1],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            fixedrange=True,
        ),
        barmode="overlay",
        bargap=0,
        hovermode="x unified",
        template="plotly_white",
    )

    return fig


def plot_price_indices_contracting_status_15min(
    df_15min: pd.DataFrame,
) -> go.Figure:
    """Tworzy interaktywny wykres Plotly dla danych 15-minutowych."""
    return _build_price_indices_chart(
        df=df_15min,
        interval_minutes=15,
        title="Indeksy cenowe i stan zakontraktowania (15-minutowe)",
    )


def plot_price_indices_contracting_status_1h(df_1h: pd.DataFrame) -> go.Figure:
    """Tworzy interaktywny wykres Plotly dla danych 1-godzinnych."""
    return _build_price_indices_chart(
        df=df_1h,
        interval_minutes=60,
        title="Indeksy cenowe i stan zakontraktowania (Godzinowe)",
    )


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
