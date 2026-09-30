import streamlit as st

from src.app.data_provider import get_news_articles, get_news_digest, get_dates_of_summaries
from src.app.layout import render_page_header


available_dates = sorted(list(get_dates_of_summaries()))
ICON = {"up": "📈", "down": "📉", "neutral": "➖", "unclear": "❓"}
COMMODITY = {"power": "energia", "gas": "gaz", "oil": "ropa", "co2": "CO2", "general": "ogólne"}


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

if digest is not None:
    news = digest["items"][0]

    tab1, tab2 = st.tabs(["Short term", "Long term"])

    with tab1:
        st.markdown("## Rynek Short-Term")
        if any(n.get("horizon") == "short" for n in news):
            for each_news in news:
                if each_news["horizon"] == "short":
                    links = ", ".join(
                        f"[{s['source'] or s['id']}]({s['url']})" for s in each_news["sources"]
                    )
                    st.markdown(
                        f"{ICON[each_news['impact']]} **{COMMODITY[each_news['commodity']]}**: {each_news['summary']}  \n{links}"
                    )
        else:
            st.info("Brak podsumowania dla tego rynku")
    with tab2:
        st.markdown("## Rynek Long-Term")
        if any(n.get("horizon") == "long" for n in news):
            for each_news in news:
                if each_news["horizon"] == "long":
                    links = ", ".join(
                        f"[{s['source'] or s['id']}]({s['url']})" for s in each_news["sources"]
                    )
                    st.markdown(
                        f"{ICON[each_news['impact']]} **{COMMODITY[each_news['commodity']]}**: {each_news['summary']}  \n{links}"
                    )
        else:
            st.info("Brak podsumowania dla tego rynku")
else:
    st.info("Brak podsumowania. Worker ETL jeszcze go nie wygenerował.")
