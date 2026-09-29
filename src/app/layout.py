import streamlit as st


def apply_custom_styles():
    st.markdown(
        """
        <style>
        footer {visibility: hidden;}
        [data-testid="stMetric"], div[data-testid="metric-container"] {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(255,255,255,0.05);
            border-left: 4px solid #00E676; /* Neonowy akcent z lewej */
            padding: 1rem;
            border-radius: 6px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            transition: transform 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px); /* Delikatne uniesienie po najechaniu */
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.9rem !important;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #94a3b8;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
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
