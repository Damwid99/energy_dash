import streamlit as st

page_home = st.Page("pages/home.py", title="Strona Główna", icon="🏠", default=True)
page_prices = st.Page("pages/1_Analiza_cenowa.py", title="Analiza cenowa", icon="📈")

pg = st.navigation([page_home, page_prices])
pg.run()
