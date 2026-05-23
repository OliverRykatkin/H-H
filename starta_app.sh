#!/bin/bash
# Starta Riksdagsprediction-appen
cd "$(dirname "$0")"

# Kontrollera att Python är installerat
if ! command -v python3 &> /dev/null; then
    echo "Python 3 krävs. Installera det från https://python.org"
    exit 1
fi

# Installera beroenden om de saknas
echo "Installerar beroenden..."
pip install -r requirements.txt -q

# Starta Streamlit-appen
echo "Startar Riksdagsprediction..."
python3 -m streamlit run app.py --server.port 8501
