import streamlit as st

from src.app.layout import render_page_header

render_page_header("O projekcie")

st.markdown(
    """
## Energy Dash

Energy Dash to panel analityczny polskiego rynku energii elektrycznej.
Aplikacja łączy dane rynkowe, informacje o aktywach odnawialnych oraz
automatycznie generowane podsumowania najważniejszych wydarzeń rynkowych.

### Co znajdziesz w aplikacji?

- ceny energii z rynku polskiego,
- dane RCE i CEN publikowane przez PSE,
- Fixing I, Fixing II oraz wolumeny z TGE,
- analizę zmienności cen i profili dobowych,
- analizę generacji farm wiatrowych i fotowoltaicznych,
- współczynniki wykorzystania mocy oraz jakość prognoz,
- aktualności dotyczące energii, gazu, ropy i uprawnień do emisji CO2,
- krótkoterminowe i długoterminowe podsumowania newsów generowane przez LLM.

### Zakładki

**Strona główna**  
Bieżące i historyczne wskaźniki cenowe oraz szybki podgląd sytuacji rynkowej.

**Analiza cenowa**  
Porównanie indeksów cenowych, profile dobowe, spread cenowy, heatmapy
oraz analiza okresów PEAK i BASE.

**Analiza aktywów wytwórczych**  
Mapa przykładowych farm OZE, dane generacji, prognozy i metryki błędu.

**Newsy rynkowe**  
Wyselekcjonowane informacje rynkowe podzielone według horyzontu wpływu
na ceny energii.

### Dane i aktualizacja

Dane są pobierane automatycznie przez proces ETL działający w tle.
Znaczniki czasu są przechowywane w UTC, a prezentowane w strefie
`Europe/Warsaw`.

Aplikacja korzysta między innymi z następujących źródeł:

- PSE,
- TGE,
- Google News RSS,
- lokalnych plików CSV z przykładowymi danymi aktywów OZE.

Częstotliwość aktualizacji zależy od źródła oraz jego dostępności.
Brak danych w konkretnym widoku może oznaczać opóźnienie publikacji,
chwilową niedostępność źródła albo brak danych historycznych.

### Technologia

Projekt został zbudowany z wykorzystaniem:

- Python,
- Streamlit,
- PostgreSQL,
- SQLAlchemy,
- Pandas,
- Plotly,
- APScheduler,
- LiteLLM i modeli językowych,
- Docker Compose.

Kod źródłowy projektu jest dostępny na GitHubie:

[github.com/Damwid99/energy_dash](https://github.com/Damwid99/energy_dash)

### Ważna informacja

Aplikacja ma charakter demonstracyjny, edukacyjny i analityczny.
Prezentowane dane, wykresy i podsumowania nie stanowią rekomendacji
inwestycyjnej, handlowej ani operacyjnej.

Dane pochodzą ze źródeł zewnętrznych i mogą być opóźnione, niepełne
albo czasowo niedostępne. Przed wykorzystaniem komercyjnym należy
sprawdzić aktualne warunki korzystania z poszczególnych źródeł danych.

Projekt open source:

[Licencja MIT](https://github.com/Damwid99/energy_dash/blob/main/LICENSE)
"""
)
