import streamlit as st


def apply_custom_styles():
    st.markdown(
        """
        <style>
        footer {visibility: hidden;}
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenu"],
        [data-testid="stToolbarActions"] {display: none;}

        /* Mniej pustego miejsca u góry */
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}

        /* Karty KPI */
        [data-testid="stMetric"], div[data-testid="metric-container"] {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128,128,128,0.2);
            padding: 0.9rem 1rem;
            border-radius: 8px;
        }
        [data-testid="stMetricLabel"] {opacity: 0.7;}

        /* Wykresy Plotly w zaokrąglonej ramce bez niechcianego paska przewijania */
        [data-testid="stPlotlyChart"] {
            border: 1px solid rgba(128,128,128,0.2);
            border-radius: 8px;
            overflow: hidden;
            box-sizing: border-box;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_footer(last_update=None):
    st.sidebar.divider()
    lines = [
        "**Dashboard Rynku Energii** ⚡",
        "Stworzone przez: [Damwid99](https://github.com/Damwid99)",
    ]
    if last_update is not None:
        lines.append(f"Dane do: `{last_update:%Y-%m-%d %H:%M}`")
    st.sidebar.markdown("\n\n".join(lines))


def render_page_header(title: str, subtitle: str = "", icon: str = ""):
    st.title(f"{icon} {title}".strip())
    if subtitle:
        st.caption(subtitle)
    st.divider()
