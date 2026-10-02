# GitHub Actions → AWS via OIDC. Inga långlivade nycklar.
# publish-rollen: bara main-grenen; preview-rollen: pull requests, bara previews/-prefixet.

# OIDC-providern finns en gång per konto: den miljö som sätts upp först skapar den
# (create_github_oidc_provider = true), den andra slår upp den.
data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  oidc_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "trust_main" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "trust_pr" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:pull_request"]
    }
  }
}

resource "aws_iam_role" "publish" {
  name                 = "${local.prefix}-github-publish"
  assume_role_policy   = data.aws_iam_policy_document.trust_main.json
  max_session_duration = 3600
}

resource "aws_iam_role" "preview" {
  name               = "${local.prefix}-github-preview"
  assume_role_policy = data.aws_iam_policy_document.trust_pr.json
}

data "aws_iam_policy_document" "publish" {
  statement {
    sid       = "WriteBuckets"
    actions   = ["s3:PutObject", "s3:PutObjectTagging", "s3:GetObject", "s3:GetObjectTagging"]
    resources = ["${aws_s3_bucket.site.arn}/*", "${aws_s3_bucket.data.arn}/*"]
  }
  statement {
    sid       = "ListBuckets"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.site.arn, aws_s3_bucket.data.arn]
  }
  # Sajtbygget tar bort sidor som inte längre finns. Datalagret raderas aldrig (releaser är oföränderliga).
  statement {
    sid       = "PruneSite"
    actions   = ["s3:DeleteObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
  }
  statement {
    sid       = "Invalidate"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [aws_cloudfront_distribution.site.arn, aws_cloudfront_distribution.data.arn]
  }
}

data "aws_iam_policy_document" "preview" {
  statement {
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.site.arn}/previews/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.site.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["previews/*"]
    }
  }
}

resource "aws_iam_role_policy" "publish" {
  role   = aws_iam_role.publish.id
  policy = data.aws_iam_policy_document.publish.json
}

resource "aws_iam_role_policy" "preview" {
  role   = aws_iam_role.preview.id
  policy = data.aws_iam_policy_document.preview.json
}
