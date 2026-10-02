# En distribution per domän. Cache-Control sätts per objekt vid uppladdning
# (immutable för hashade filer, s-maxage=5 för manifest) och respekteras här.

# Egen policy i stället för den hanterade UseOriginCacheControlHeaders: den lägger Host
# i cachenyckeln och skickar då vidare besökarens Host till S3, som svarar NotFound.
resource "aws_cloudfront_cache_policy" "origin_headers" {
  name        = "${local.prefix}-origin-cache-control"
  min_ttl     = 0
  default_ttl = 60
  max_ttl     = 31536000
  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
  }
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "${local.prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "data_cors" {
  name = "${local.prefix}-data-cors"
  cors_config {
    access_control_allow_credentials = false
    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD", "OPTIONS"]
    }
    access_control_allow_origins {
      # Öppen data: alla får läsa (CC BY-NC). Sajtens egna origins listas för tydlighet.
      items = ["*"]
    }
    access_control_expose_headers {
      items = ["ETag", "Content-Length"]
    }
    access_control_max_age_sec = 86400
    origin_override            = true
  }
  security_headers_config {
    content_type_options {
      override = true
    }
    strict_transport_security {
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      override                   = true
    }
  }
}

# Astro-bygget: /parti/m/ → /parti/m/index.html
resource "aws_cloudfront_function" "index_rewrite" {
  name    = "${local.prefix}-index-rewrite"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-JS
    function handler(event) {
      var req = event.request;
      if (req.uri.endsWith('/')) { req.uri += 'index.html'; }
      else if (!req.uri.split('/').pop().includes('.')) { req.uri += '/index.html'; }
      return req;
    }
  JS
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${local.prefix} sajt"
  aliases             = local.site_aliases
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "site"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  default_cache_behavior {
    target_origin_id           = "site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.origin_headers.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.index_rewrite.arn
    }
  }

  # Hashade Astro-tillgångar
  ordered_cache_behavior {
    path_pattern               = "/_astro/*"
    target_origin_id           = "site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security.id
  }

  custom_error_response {
    error_code         = 403
    response_code      = 404
    response_page_path = "/404.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 404
    response_page_path = "/404.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

resource "aws_cloudfront_distribution" "data" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "${local.prefix} data"
  aliases         = [local.data_domain]
  price_class     = "PriceClass_100"
  http_version    = "http2and3"

  origin {
    domain_name              = aws_s3_bucket.data.bucket_regional_domain_name
    origin_id                = "data"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  default_cache_behavior {
    target_origin_id           = "data"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD", "OPTIONS"]
    compress                   = true
    cache_policy_id            = aws_cloudfront_cache_policy.origin_headers.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.data_cors.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.data.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
