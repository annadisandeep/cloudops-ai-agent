# AWS stack (disabled by default): least-privilege READ-ONLY IAM policy and
# role for the agent's AWS adapter. No compute is provisioned here.

data "aws_iam_policy_document" "agent_readonly" {
  statement {
    sid    = "Ec2DescribeReadOnly"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeTags",
    ]
    resources = ["*"] # Describe* APIs do not support resource-level scoping
  }

  statement {
    sid    = "CloudWatchReadOnly"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CloudWatchLogsReadOnly"
    effect = "Allow"
    actions = [
      "logs:FilterLogEvents",
      "logs:GetLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "agent_readonly" {
  count       = var.enable_aws ? 1 : 0
  name        = "cloudops-agent-readonly"
  description = "CloudOps AI Agent — strictly read-only observability access"
  policy      = data.aws_iam_policy_document.agent_readonly.json
}

data "aws_iam_policy_document" "agent_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [var.enable_aws ? "arn:aws:iam::000000000000:root" : "arn:aws:iam::000000000000:root"]
      # Replace with the principal that runs the backend (set via tfvars).
    }
  }
}

resource "aws_iam_role" "agent_readonly" {
  count              = var.enable_aws ? 1 : 0
  name               = "cloudops-agent-readonly"
  assume_role_policy = data.aws_iam_policy_document.agent_assume.json
}

resource "aws_iam_role_policy_attachment" "agent_readonly" {
  count      = var.enable_aws ? 1 : 0
  role       = aws_iam_role.agent_readonly[0].name
  policy_arn = aws_iam_policy.agent_readonly[0].arn
}
