FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Labbet ska inte indexeras (den publika sajten är mandatorn.se).
RUN python -c "import pathlib, streamlit; p = pathlib.Path(streamlit.__file__).parent / 'static' / 'index.html'; t = p.read_text(encoding='utf-8'); assert '<head>' in t; p.write_text(t.replace('<head>', '<head><meta name=\"robots\" content=\"noindex,nofollow\">', 1), encoding='utf-8')"

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD streamlit run app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
