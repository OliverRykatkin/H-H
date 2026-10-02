# Certifikat (us-east-1) och DNS. Med manage_dns = false skapas inga Route 53-poster;
# valideringsposterna och CNAME-målen skrivs då ut som outputs för manuell inläggning.

resource "aws_route53_zone" "root" {
  count = var.manage_dns && var.environment == "prod" ? 1 : 0
  name  = var.root_domain
}

data "aws_route53_zone" "root" {
  count = var.manage_dns && var.environment != "prod" ? 1 : 0
  name  = var.root_domain
}

locals {
  zone_id = var.manage_dns ? (var.environment == "prod" ? aws_route53_zone.root[0].zone_id : data.aws_route53_zone.root[0].zone_id) : null
}

resource "aws_acm_certificate" "site" {
  provider                  = aws.us_east_1
  domain_name               = local.site_aliases[0]
  subject_alternative_names = slice(local.site_aliases, 1, length(local.site_aliases))
  validation_method         = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "data" {
  provider          = aws.us_east_1
  domain_name       = local.data_domain
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

locals {
  validation_records = {
    for dvo in concat(tolist(aws_acm_certificate.site.domain_validation_options),
    tolist(aws_acm_certificate.data.domain_validation_options)) :
    dvo.domain_name => { name = dvo.resource_record_name, type = dvo.resource_record_type, value = dvo.resource_record_value }
  }
}

resource "aws_route53_record" "validation" {
  for_each        = var.manage_dns ? local.validation_records : {}
  zone_id         = local.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = var.manage_dns ? [for d in aws_acm_certificate.site.domain_validation_options : aws_route53_record.validation[d.domain_name].fqdn] : null
}

resource "aws_acm_certificate_validation" "data" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.data.arn
  validation_record_fqdns = var.manage_dns ? [for d in aws_acm_certificate.data.domain_validation_options : aws_route53_record.validation[d.domain_name].fqdn] : null
}

resource "aws_route53_record" "site" {
  for_each = var.manage_dns ? toset(local.site_aliases) : toset([])
  zone_id  = local.zone_id
  name     = each.value
  type     = "A"
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_aaaa" {
  for_each = var.manage_dns ? toset(local.site_aliases) : toset([])
  zone_id  = local.zone_id
  name     = each.value
  type     = "AAAA"
  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "data" {
  for_each = var.manage_dns ? toset(["A", "AAAA"]) : toset([])
  zone_id  = local.zone_id
  name     = local.data_domain
  type     = each.value
  alias {
    name                   = aws_cloudfront_distribution.data.domain_name
    zone_id                = aws_cloudfront_distribution.data.hosted_zone_id
    evaluate_target_health = false
  }
}

# Poster som fanns hos One.com och flyttas med till Route 53 (prod).
resource "aws_route53_record" "root_txt" {
  count   = var.manage_dns && var.environment == "prod" ? 1 : 0
  zone_id = local.zone_id
  name    = var.root_domain
  type    = "TXT"
  ttl     = 3600
  records = ["google-site-verification=8HTRUvMp6EQi-pJJMdMQIxbgKU7HKuGMdnPrCuyJTBk"]
}

# Null-MX (RFC 7505): domänen tar inte emot e-post.
resource "aws_route53_record" "root_mx" {
  count   = var.manage_dns && var.environment == "prod" ? 1 : 0
  zone_id = local.zone_id
  name    = var.root_domain
  type    = "MX"
  ttl     = 3600
  records = ["0 ."]
}
