# Live-nowcast på valnatten (fas 3). Byggs med repo-roten som kontext:
#   fly deploy --config deploy/nowcast/fly.toml --dockerfile deploy/nowcast/Dockerfile .
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements-pipeline.txt .
RUN pip install -r requirements-pipeline.txt

# Modellpaketet + det som läses vid import och vid publicering av nowcast-releaser:
# constants (election_2026.json), text (contracts/verbal_scale.json), baslinjen per distrikt.
COPY mandatorn_model/ mandatorn_model/
COPY contracts/verbal_scale.json contracts/verbal_scale.json
COPY data/election_2026.json data/baseline_districts_2026.csv.gz data/
COPY data/muni_structure_2026.json data/muni_structure_2022.json data/

# Ingen HTTP-tjänst: en worker som pollar Valmyndigheten och publicerar till datalagret.
# OUT, DATA_DISTRIBUTION_ID och AWS_ROLE_ARN sätts med `fly secrets set` (se README.md).
CMD python -m mandatorn_model.nowcast_live \
    --out "$OUT" --year "$YEAR" --election "$ELECTION" --interval "$INTERVAL" \
    ${DATA_DISTRIBUTION_ID:+--distribution-id "$DATA_DISTRIBUTION_ID"}
