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
page_assets_analysis = st.Page(
    "pages/2_Analiza_asetow_wytworczych.py", title="Analiza assetow wytworczych", icon="📈"
)
page_news = st.Page("pages/3_Newsy_rynkowe.py", title="Newsy rynkowe", icon="📰")
page_procject_info = st.Page("pages/0_O_projekcie.py", title="O projekcie", icon="ℹ️")

g = st.navigation([page_home, page_prices, page_assets_analysis, page_news, page_procject_info])
g.run()

render_sidebar_footer()
