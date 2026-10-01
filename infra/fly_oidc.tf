# Fly.io → AWS via OIDC för live-nowcasten (fas 3). Inga långlivade nycklar.
# Aktiveras genom att sätta var.fly_org (Fly-organisationens slug); annars skapas inget.
# Antagande (verifiera mot Fly-dok): issuer https://oidc.fly.io/<org>, sub "<org>:<app>:<maskin>".

locals {
  fly_enabled = var.fly_org != ""
  fly_issuer  = "oidc.fly.io/${var.fly_org}"
}

resource "aws_iam_openid_connect_provider" "fly" {
  count          = local.fly_enabled ? 1 : 0
  url            = "https://${local.fly_issuer}"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "trust_fly" {
  count = local.fly_enabled ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.fly[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.fly_issuer}:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "${local.fly_issuer}:sub"
      values   = ["${var.fly_org}:${var.fly_app}:*"]
    }
  }
}

resource "aws_iam_role" "fly_nowcast" {
  count                = local.fly_enabled ? 1 : 0
  name                 = "${local.prefix}-fly-nowcast"
  assume_role_policy   = data.aws_iam_policy_document.trust_fly[0].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "fly_nowcast" {
  statement {
    sid       = "WriteData"
    actions   = ["s3:PutObject", "s3:PutObjectTagging", "s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
  }
  statement {
    sid       = "ListData"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data.arn]
  }
  statement {
    sid       = "InvalidateData"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [aws_cloudfront_distribution.data.arn]
  }
}

resource "aws_iam_role_policy" "fly_nowcast" {
  count  = local.fly_enabled ? 1 : 0
  role   = aws_iam_role.fly_nowcast[0].id
  policy = data.aws_iam_policy_document.fly_nowcast.json
}
