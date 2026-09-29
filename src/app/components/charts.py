import numpy as np
import pandas as pd
import plotly.graph_objects as go


def get_background_colors(
    status_series, pos_color="rgba(59, 130, 246, 0.25)", neg_color="rgba(239, 68, 68, 0.25)"
):
    conditions = [status_series > 0, status_series < 0]
    choices = [pos_color, neg_color]
    return np.select(conditions, choices, default="rgba(0,0,0,0)")


def _build_price_indices_chart(df: pd.DataFrame, interval_minutes: int, title: str) -> go.Figure:
    """Prywatna funkcja pomocnicza budująca wykres Plotly dla zadanego interwału.

    Wykorzystuje czysto wektorowe przekształcenia oraz bezpieczną obsługę brakujących wartości.
    """
    fig = go.Figure()

    # Wektorowe wyznaczenie wysokości słupków - tylko tam, gdzie kse_contracting_status != 0
    status = df["kse_contracting_status"].fillna(0)
    y_bar = np.where(status != 0, 1, np.nan)

    # Szerokość słupka w ms dla Plotly
    bar_width_ms = interval_minutes * 60 * 1000

    # --- SERIA SŁUPKOWA (TŁO) ---
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=y_bar,
            yaxis="y2",
            marker_color=get_background_colors(df["kse_contracting_status"]),
            marker_line_width=0,  # Bez obramowania słupków
            width=bar_width_ms,
            name="Stan zakontraktowania",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # --- SERIE LINIOWE (INDEKSY CENOWE) ---
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["fixing_1_pln_mwh"],
            mode="lines",
            name="Fixing I",
            line=dict(color="#1f77b4"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["fixing_2_pln_mwh"],
            mode="lines",
            name="Fixing II",
            line=dict(color="#ff7f0e"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
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
