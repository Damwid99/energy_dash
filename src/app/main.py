import streamlit as st

from src.app.layout import apply_custom_styles, render_sidebar_footer

st.set_page_config(
    page_title="Dashboard Energetyczny",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_styles()

page_home = st.Page("pages/home.py", title="Strona Główna", icon="🏠", default=True)
page_prices = st.Page("pages/1_Analiza_cenowa.py", title="Analiza cenowa", icon="📈")

g = st.navigation([page_home, page_prices])
g.run()

render_sidebar_footer()
