import numpy as np
import pandas as pd
import plotly.graph_objects as go


def get_background_colors(
    status_series, pos_color="rgba(59, 130, 246, 0.25)", neg_color="rgba(239, 68, 68, 0.25)"
):
    conditions = [status_series > 0, status_series < 0]
    choices = [pos_color, neg_color]
    return np.select(conditions, choices, default="rgba(0,0,0,0)")


def plot_price_indices_contracting_status(df_15min: pd.DataFrame, df_1h: pd.DataFrame) -> go.Figure:
    """
    Tworzy interaktywny wykres Plotly przedstawiający indeksy cenowe oraz stan zakontraktowania KSE.

    Funkcja generuje wykres liniowy dla cen (Fixing I, Fixing II, CEN) nałożony na wykres
    słupkowy pełniący rolę tła, który wizualizuje stan zakontraktowania. Zawiera wbudowane menu (updatemenus)
    pozwalające na płynne przełączanie między danymi 15-minutowymi a godzinowymi.

    Args:
        df_15min (pd.DataFrame): Ramka danych z agregacją 15-minutową. Wymaga indeksu
            czasowego (datetime) oraz kolumn: 'fixing_1_pln_mwh', 'fixing_2_pln_mwh',
            'cen_pln_mwh', 'kse_contracting_status'.
        df_1h (pd.DataFrame): Ramka danych z agregacją 1-godzinną o identycznej
            strukturze kolumn i indeksu jak df_15min.

    Returns:
        go.Figure: Skonfigurowany obiekt wykresu Plotly z dwiema osiami Y, menu
            przycisków i zdefiniowanymi widocznościami poszczególnych serii.
    """

    fig_price_indices_contracting_status = go.Figure()

    # --- SERIE 15-MINUTOWE ---
    fig_price_indices_contracting_status.add_trace(
        go.Bar(
            x=df_15min.index,
            y=[1] * len(df_15min),
            yaxis="y2",
            marker_color=get_background_colors(df_15min["kse_contracting_status"]),
            width=15 * 60 * 1000,
            name="Stan zakontraktowania",
            hoverinfo="skip",
            showlegend=False,
            visible=True,
        )
    )

    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_15min.index,
            y=df_15min["fixing_1_pln_mwh"],
            mode="lines",
            name="Fixing I",
            line=dict(color="#1f77b4"),
            visible=True,
        )
    )
    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_15min.index,
            y=df_15min["fixing_2_pln_mwh"],
            mode="lines",
            name="Fixing II",
            line=dict(color="#ff7f0e"),
            visible=True,
        )
    )
    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_15min.index,
            y=df_15min["cen_pln_mwh"],
            mode="lines",
            name="CEN",
            line=dict(color="#2ca02c"),
            visible=True,
        )
    )

    # --- SERIE GODZINOWE ---
    fig_price_indices_contracting_status.add_trace(
        go.Bar(
            x=df_1h.index,
            y=[1] * len(df_1h),
            yaxis="y2",
            marker_color=get_background_colors(df_1h["kse_contracting_status"]),
            width=60 * 60 * 1000,
            name="Tło 1h",
            hoverinfo="skip",
            showlegend=False,
            visible=False,
        )
    )

    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_1h.index,
            y=df_1h["fixing_1_pln_mwh"],
            mode="lines",
            name="Fixing I (1h)",
            line=dict(color="#1f77b4"),
            visible=False,
        )
    )
    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_1h.index,
            y=df_1h["fixing_2_pln_mwh"],
            mode="lines",
            name="Fixing II (1h)",
            line=dict(color="#ff7f0e"),
            visible=False,
        )
    )
    fig_price_indices_contracting_status.add_trace(
        go.Scatter(
            x=df_1h.index,
            y=df_1h["cen_pln_mwh"],
            mode="lines",
            name="CEN (1h)",
            line=dict(color="#2ca02c"),
            visible=False,
        )
    )

    fig_price_indices_contracting_status.update_layout(
        title="Indeksy cenowe oraz stan zakontraktowania KSE",
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
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                buttons=[
                    dict(
                        label="15 Minut",
                        method="update",
                        args=[
                            {"visible": [True, True, True, True, False, False, False, False]},
                            {"title": "Indeksy cenowe i stan zakontraktowania (15-minutowe)"},
                        ],
                    ),
                    dict(
                        label="1 Godzina",
                        method="update",
                        args=[
                            {"visible": [False, False, False, False, True, True, True, True]},
                            {"title": "Indeksy cenowe i stan zakontraktowania (Godzinowe)"},
                        ],
                    ),
                ],
                pad={"r": 10, "t": 10},
                showactive=True,
                x=0.0,
                xanchor="left",
                y=1.15,
                yanchor="top",
            )
        ],
    )
    return fig_price_indices_contracting_status
