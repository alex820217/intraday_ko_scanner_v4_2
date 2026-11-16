# KO Market Radar V4.2

## Dateien ins GitHub-Root
- `intraday_ko_scanner_v4_2.py`
- `market_universe.py`
- `ko_trade_profile.py`
- `product_resolver.py`
- `position_manager.py`
- `requirements.txt`

## Streamlit Community Cloud
- Repository auswählen
- Main file path: `intraday_ko_scanner_v4_2.py`
- Deploy

## Standard-Handelsprofil
- Einsatz: 1.000–2.000 EUR, Plan 1.500 EUR
- Hebel: 4–6x
- KO-Abstand: 17–23 %
- Stop: -5 %, absolute Grenze -8 %
- Ziel: +10 %
- Trailing: +5 % → Break-even, +10 % → Stop +5 %, +15 % → Stop +10 %

## Hinweis zur Speicherung
`positions.json` und `trade_history.json` sind auf Streamlit Community Cloud nicht dauerhaft. Die Funktion ist für den Testbetrieb enthalten. Für Persistenz später Supabase anbinden.
