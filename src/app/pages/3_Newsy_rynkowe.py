import streamlit as st

from src.app.data_provider import get_news_articles, get_news_digest, get_dates_of_summaries
from src.app.layout import render_page_header
from src.app.components.utils import render_items, ICON, COMMODITY


available_dates = get_dates_of_summaries()

if not available_dates:
    render_page_header("Newsy rynkowe")
    st.info("Brak podsumowania. Worker ETL jeszcze go nie wygenerował.")
    st.stop()

with st.sidebar:
    st.header("Opcje")
    selected_date = st.date_input(
        "Wybierz dzień",
        value=available_dates[-1],
        min_value=available_dates[0],
        max_value=available_dates[-1],
    )
    if selected_date not in available_dates:
        st.error("Brak danych dla wybranej daty. Wybierz dzień dostępny w bazie.")
        st.stop()

render_page_header(f"Newsy rynkowe na dzień {selected_date}")

digest = get_news_digest(selected_date)

if digest is None:
    st.info("Brak podsumowania dla wybranego dnia.")
    st.stop()

st.caption(
    f"Wygenerowano: {digest['generated_utc']:%Y-%m-%d %H:%M} UTC | model: {digest['model']} | "
    f"artykułów: {digest['n_articles']}"
)

tab1, tab2 = st.tabs(["Short term", "Long term"])
with tab1:
    st.markdown("## Rynek Short-Term")
    render_items(digest["items"], "short")
with tab2:
    st.markdown("## Rynek Long-Term")
    render_items(digest["items"], "long")

st.caption(
    "📈 wzrost cen, 📉 spadek, ➖ neutralnie, ❓ niejasne (wpływ na ceny energii w Polsce). "
    "Podsumowanie wygenerowane automatycznie, może zawierać błędy."
)
