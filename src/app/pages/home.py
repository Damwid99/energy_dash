import streamlit as st
from src.app.layout import render_page_header

render_page_header("System analityczny Rynku Energii")
st.markdown(
    """
    ### O projekcie
    Panel analityczny polskiego systemu elektroenergetycznego stworzony w celach demonstracyjnych i rekrutacyjnych. Aplikacja monitoruje i wizualizuje dane rynkowe w czasie zbliżonym do rzeczywistego.

    > **Informacja:** Prezentowane dane oraz wskaźniki mają charakter poglądowy.

    📦 **Repozytorium kodu:** [github.com/Damwid99/energy_dash](https://github.com/Damwid99/energy_dash)
    """
)
