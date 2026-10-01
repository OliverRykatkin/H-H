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

output "manual_dns_records" {
  description = "Om manage_dns = false: lägg in dessa poster hos DNS-leverantören"
  value = var.manage_dns ? {} : {
    certificate_validation = local.validation_records
    cnames = merge(
      { for a in local.site_aliases : a => aws_cloudfront_distribution.site.domain_name },
      { (local.data_domain) = aws_cloudfront_distribution.data.domain_name },
    )
  }
}
