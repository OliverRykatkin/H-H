output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "data_bucket" {
  value = aws_s3_bucket.data.bucket
}

output "site_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "data_distribution_id" {
  value = aws_cloudfront_distribution.data.id
}

output "site_cloudfront_domain" {
  value = aws_cloudfront_distribution.site.domain_name
}

output "data_cloudfront_domain" {
  value = aws_cloudfront_distribution.data.domain_name
}

output "github_publish_role_arn" {
  description = "Sätts som repo-variabeln AWS_ROLE_ARN (prod) / AWS_ROLE_ARN_STAGING"
  value       = aws_iam_role.publish.arn
}

output "github_preview_role_arn" {
  value = aws_iam_role.preview.arn
}

output "route53_name_servers" {
  description = "Peka domänen hos One.com till dessa namnservrar (prod, manage_dns = true)"
  value       = var.manage_dns && var.environment == "prod" ? aws_route53_zone.root[0].name_servers : []
}

output "certificate_validation_records" {
  description = "Om manage_dns = false: CNAME-poster att lägga in hos DNS-leverantören för certifikatvalideringen"
  value       = var.manage_dns ? null : local.validation_records
}

output "manual_dns_cnames" {
  description = "Om manage_dns = false: CNAME-poster som pekar domänerna mot CloudFront"
  value = var.manage_dns ? null : merge(
    { for a in local.site_aliases : a => aws_cloudfront_distribution.site.domain_name },
    { (local.data_domain) = aws_cloudfront_distribution.data.domain_name },
  )
}

output "fly_nowcast_role_arn" {
  description = "Sätts som Fly-hemligheten AWS_ROLE_ARN för mandatorn-nowcast (tom om fly_org saknas)"
  value       = local.fly_enabled ? aws_iam_role.fly_nowcast[0].arn : ""
}
