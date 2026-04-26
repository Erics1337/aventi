# Aventi AWS Terraform

This directory now manages a dev-first AWS baseline:
- ECR repositories with lifecycle cleanup
- CloudWatch log groups
- ECS cluster, IAM roles, and API/worker task definitions
- Optional runtime secret placeholder
- Optional API service and ALB, both disabled by default

The default Terraform path keeps the account near-zero cost while still making
the deployment shape explicit in code.

This Terraform belongs to the `aventi` repo and should only manage Aventi AWS
infrastructure. Separate products or sites should keep their own infrastructure
code in their own repos so we do not couple unrelated stacks together.
