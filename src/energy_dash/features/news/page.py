from datetime import date

import streamlit as st

from energy_dash.app.layout import render_page_caution, render_page_header
from energy_dash.features.news.queries import (
    get_dates_of_summaries,
    get_news_digest,
)
from energy_dash.features.news.ui import render_items


@st.cache_data(ttl=300)
def _cached_news_digest(issued_day: date):
    return get_news_digest(issued_day=issued_day)


@st.cache_data(ttl=300)
def _cached_dates_of_summaries():
    return get_dates_of_summaries()


def render_news():
    available_dates = _cached_dates_of_summaries()

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

    digest = _cached_news_digest(selected_date)

    if digest is None:
        st.info("Brak podsumowania dla wybranego dnia.")
        st.stop()

    text = f"""
    Analiza artykułów została wygenerowana przez AI. Analiza nie stanowi rekomendacji biznesowej - ma charakter wyłącznie poglądowy. \n
    Wygenerowano: {digest["generated_utc"]:%Y-%m-%d %H:%M} UTC | model: {digest["model"]} | artykułów: {digest["n_articles"]}
    """
    render_page_caution("UWAGA", text)

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
