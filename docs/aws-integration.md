# AWS Read-Only Integration

Status: **implemented and mock-tested** — not yet verified against a live account. Demo mode emulates AWS-shaped resources without any of this setup.

## What the adapter uses

| Capability | API | Call |
|---|---|---|
| Inventory | EC2 | `DescribeInstances` (paginator, bounded) |
| Metrics | CloudWatch | `GetMetricStatistics` |
| Logs | CloudWatch Logs | `FilterLogEvents` on `/cloudops/<instance-id>` log groups |

Metric mapping: `cpu_utilization`, `network_in_bytes`, `network_out_bytes` are built-in EC2 metrics. `memory_available_mb` and `disk_used_percent` require the **CloudWatch agent** publishing to the `CWAgent` namespace.

## Setup

1. Create an IAM identity with a strictly read-only policy (the exact policy is codified in [infrastructure/terraform/aws.tf](../infrastructure/terraform/aws.tf)):
   `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`, `ec2:DescribeTags`,
   `cloudwatch:GetMetricStatistics|GetMetricData|ListMetrics`,
   `logs:FilterLogEvents|GetLogEvents|DescribeLogGroups|DescribeLogStreams`.
2. Provide credentials on the **server** via the standard boto3 chain (env vars, `~/.aws/credentials` profile, or an instance/task role). Never put them in the frontend or the repo.
3. Configure and restart the backend:
   ```env
   CLOUDOPS_AWS_ENABLED=true
   CLOUDOPS_AWS_ALLOWED_ACCOUNTS=123456789012
   CLOUDOPS_AWS_REGION=us-east-1
   ```

Fail-closed behavior: at adapter construction the backend calls STS `GetCallerIdentity` and rejects the session unless the account is in the allowlist. Empty allowlist → every AWS request is 403.

## Verification checklist (when you have a real account)

```powershell
curl "http://localhost:8000/api/v1/resources?provider=aws"
curl "http://localhost:8000/api/v1/metrics?provider=aws&resource_id=<i-...>&metric=cpu_utilization"
```

Update the README feature table from "mock-tested" to "live-verified" once this passes.
