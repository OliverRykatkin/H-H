# Budgetlarm från dag ett + larm på ovanligt hög CloudFront-trafik.

resource "aws_budgets_budget" "monthly" {
  name         = "${local.prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:project$mandatorn"]
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_sns_topic" "alarms" {
  provider = aws.us_east_1
  name     = "${local.prefix}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  provider  = aws.us_east_1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "cloudfront_requests" {
  provider            = aws.us_east_1
  for_each            = { site = aws_cloudfront_distribution.site.id, data = aws_cloudfront_distribution.data.id }
  alarm_name          = "${local.prefix}-${each.key}-requests-high"
  alarm_description   = "Ovanligt många förfrågningar mot ${each.key}-distributionen"
  namespace           = "AWS/CloudFront"
  metric_name         = "Requests"
  dimensions          = { DistributionId = each.value, Region = "Global" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.cloudfront_requests_alarm_per_5min
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
