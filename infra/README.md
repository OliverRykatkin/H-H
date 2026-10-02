# infra/: AWS för mandatorn.se (Terraform)

Det här skapas per miljö (`staging` eller `prod`):
- **S3:** buckets för sajt och data, utan publik åtkomst, med livscykelregler för dragningarna (D5).
- **CloudFront:** en distribution per domän, med Origin Access Control och CORS på `data.`.
- **Certifikat:** ACM-certifikat i us-east-1.
- **DNS:** Route 53 (valfritt, `manage_dns`).
- **GitHub:** OIDC-roller för Actions, en för publicering från `main` och en för förhandsvisning i PR.
- **Larm:** budgetlarm och larm på hög trafik.

## Engångsuppsättning (görs av kontoägaren)

1. Skapa en bucket för Terraform-state, till exempel `mandatorn-tfstate` i `eu-north-1`, med versionering på.
2. Aktivera kostnadstaggen `project` under *Billing → Cost allocation tags*, så att budgetfiltret fungerar.
3. Skapa variabelfiler: `cp example.tfvars staging.tfvars`. Fyll i `alert_email`. Filerna är gitignorerade.
4. Kör staging först:
   ```bash
   terraform init -backend-config="bucket=mandatorn-tfstate" -backend-config="key=mandatorn/staging.tfstate"
   terraform apply -var-file=staging.tfvars
   ```
   Prod körs på samma sätt med `key=mandatorn/prod.tfstate` och `prod.tfvars`. GitHubs OIDC-provider finns en gång per konto: miljön som sätts upp först har `create_github_oidc_provider = true` (staging här), den andra `false`.
5. Om `manage_dns = true` och prod: peka domänen hos One.com till namnservrarna i outputen `route53_name_servers` (D2). Annars görs det i två steg: kör först `terraform apply -var-file=staging.tfvars -target=aws_acm_certificate.site -target=aws_acm_certificate.data`, lägg in valideringsposterna (CNAME) från certifikatens `domain_validation_options` hos One.com, och kör sedan hela `apply`. Lägg till sist in CNAME-posterna från outputen `manual_dns_cnames`.
6. Sätt repo-variabler i GitHub (Settings → Secrets and variables → Actions → Variables):

   | Variabel | Värde |
   |---|---|
   | `AWS_ROLE_ARN` | output `github_publish_role_arn` |
   | `DATA_BUCKET` | output `data_bucket` |
   | `DATA_DISTRIBUTION_ID` | output `data_distribution_id` |
   | `SITE_BUCKET` | output `site_bucket` |
   | `SITE_DISTRIBUTION_ID` | output `site_distribution_id` |
   | `PUBLIC_DATA_URL` | `https://data.mandatorn.se` (staging: `https://data.beta.mandatorn.se`) |
   | `PUBLIC_SITE_URL` | `https://mandatorn.se` (staging: `https://beta.mandatorn.se`) |
   | `STATUS_URL` | `https://data.mandatorn.se/status.json` |

   Ping-URL:en från Healthchecks.io (D15) läggs som **hemlighet** `HEALTHCHECK_URL` (inte variabel), eftersom loggarna är publika.

   Utan `AWS_ROLE_ARN` publicerar workflowen *Publicera* bara lokalt och sparar releasen som artefakt.

## Kostnad
Se `docs/ARCHITECTURE.md`, avsnitt 9. Budgetlarmet ligger på 20 USD/månad (`monthly_budget_usd`).
