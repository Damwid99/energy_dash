import streamlit as st

from energy_dash.app.about import render as render_about
from energy_dash.app.home import render as render_home
from energy_dash.app.layout import apply_custom_styles, render_sidebar_footer
from energy_dash.features.assets.page import render as render_assets
from energy_dash.features.bess.page import render as render_bess
from energy_dash.features.market_prices.page import render as render_prices
from energy_dash.features.news.page import render as render_news

st.set_page_config(
    page_title="Dashboard Energetyczny",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_custom_styles()

pages = [
    st.Page(render_home, title="Strona Główna", icon="🏠", default=True, url_path="home"),
    st.Page(render_prices, title="Analiza cenowa", icon="📈", url_path="ceny"),
    st.Page(render_assets, title="Analiza assetów wytwórczych", icon="📈", url_path="aktywa"),
    st.Page(render_bess, title="Magazyn energii", icon="🔋", url_path="magazyn"),
    st.Page(render_news, title="Newsy rynkowe", icon="📰", url_path="newsy"),
    st.Page(render_about, title="O projekcie", icon="ℹ️", url_path="o-projekcie"),
]
st.navigation(pages).run()
render_sidebar_footer()
