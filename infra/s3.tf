# Två buckets: sajten (Astro-bygget) och data (releaser). Ingen publik åtkomst —
# all läsning går via CloudFront med Origin Access Control.

resource "aws_s3_bucket" "site" {
  bucket = "${local.prefix}-site"
}

resource "aws_s3_bucket" "data" {
  bucket = "${local.prefix}-data"
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each                = { site = aws_s3_bucket.site.id, data = aws_s3_bucket.data.id }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "all" {
  for_each = { site = aws_s3_bucket.site.id, data = aws_s3_bucket.data.id }
  bucket   = each.value
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = { site = aws_s3_bucket.site.id, data = aws_s3_bucket.data.id }
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versionering på data: skydd mot att en pekare (manifest.json) skrivs över av misstag.
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket     = aws_s3_bucket.data.id
  depends_on = [aws_s3_bucket_versioning.data]

  rule {
    id     = "drop-tagged-draws"
    status = "Enabled"
    filter {
      tag {
        key   = "retention"
        value = "draws"
      }
    }
    expiration {
      days = var.draws_retention_days
    }
  }

  rule {
    id     = "draws-daily"
    status = "Enabled"
    filter {
      prefix = "draws-daily/"
    }
    expiration {
      days = var.draws_daily_retention_days
    }
  }

  # draws-election/ saknar regel: valdagens dragningar sparas för alltid.

  rule {
    id     = "old-pointer-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 2
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    id     = "previews"
    status = "Enabled"
    filter {
      prefix = "previews/"
    }
    expiration {
      days = 14
    }
  }
}

data "aws_iam_policy_document" "site_oac" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

data "aws_iam_policy_document" "data_oac" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.data.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site_oac.json
}

resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = data.aws_iam_policy_document.data_oac.json
}
