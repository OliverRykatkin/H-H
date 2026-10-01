# deploy/nowcast: live-nowcast på Fly.io

En worker i region `arn` (Stockholm) gör följande:
1. Hämtar Valmyndighetens preliminära riksdagsfil varje minut.
2. Räknar nowcast och mandat.
3. Publicerar en release med `mode: "nowcast"` till datalagret (S3 och CloudFront).

Det sker utan fördröjning (DECISIONS D4). Koden finns i `mandatorn_model/nowcast_live.py`.

## Engångsuppsättning

1. Skapa appen: `fly apps create mandatorn-nowcast`.
2. Aktivera Fly-OIDC i Terraform:
   - Sätt `fly_org = "<din-org-slug>"` i tfvars.
   - Kör `terraform apply`.
   - Outputen `fly_nowcast_role_arn` ger rollens ARN.
3. Sätt hemligheter (inga långlivade AWS-nycklar):
   ```bash
   fly secrets set -a mandatorn-nowcast \
     OUT=s3://mandatorn-prod-data \
     DATA_DISTRIBUTION_ID=<data_distribution_id> \
     AWS_ROLE_ARN=<fly_nowcast_role_arn>
   ```
4. Bygg och deploya från repo-roten:
   ```bash
   fly deploy --config deploy/nowcast/fly.toml --dockerfile deploy/nowcast/Dockerfile .
   fly scale count 0 -a mandatorn-nowcast   # vilande tills valkvällen
   ```

## AWS-credentials via Fly OIDC

**Antagande, verifiera mot Fly-dokumentationen före valet.** Fly utfärdar OIDC-token per maskin:
- Utfärdaren är `https://oidc.fly.io/<org>`.
- `aud` är `sts.amazonaws.com`.
- `sub` har formatet `<org>:<app>:<maskin-id>`.

När hemligheten `AWS_ROLE_ARN` är satt antas Fly skriva token till `/.fly/oidc_token` och sätta `AWS_WEB_IDENTITY_TOKEN_FILE` i maskinen. boto3 använder då `AssumeRoleWithWebIdentity` automatiskt, utan nycklar. Om miljövariabeln inte sätts automatiskt går det att sätta själv: `fly secrets set AWS_WEB_IDENTITY_TOKEN_FILE=/.fly/oidc_token`.

Rollens trust-policy (`infra/fly_oidc.tf`) tillåter `sub` som matchar `<org>:mandatorn-nowcast:*`. Rollen får bara:
- skriva och läsa i data-bucketen
- lista bucketen
- invalidera data-distributionen

## Lokalt och i simulatorn

```bash
python -m mandatorn_model.publish --out dist-data                      # en prognosrelease att bygga vidare på
python -m mandatorn_model.nowcast_live --out dist-data --replay 2026 --step-minutes 30 --interval 0
```

Docker fanns inte i utvecklingsmiljön när filerna skrevs, så imagen är inte provbyggd. Kommandot i `CMD` är verifierat lokalt i simulatorläget (`--replay`).
