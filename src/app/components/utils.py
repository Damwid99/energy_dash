import streamlit as st

ICON = {"up": "📈", "down": "📉", "neutral": "➖", "unclear": "❓"}
COMMODITY = {"power": "energia", "gas": "gaz", "oil": "ropa", "co2": "CO2", "general": "ogólne"}


def calculate_farm_profile():
    pass


def render_items(items: list[dict], horizon: str):
    selected = [n for n in items if n.get("horizon") == horizon]
    if not selected:
        st.info("Brak podsumowania dla tego rynku")
        return
    for n in selected:
        links = ", ".join(f"[{s['source'] or s['id']}]({s['url']})" for s in n["sources"])
        st.markdown(
            f"{ICON.get(n['impact'], '❓')} **{COMMODITY.get(n['commodity'], n['commodity'])}**: "
            f"{n['summary']}  \n{links}"
        )
