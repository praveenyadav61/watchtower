# Optional ECR Deployment

The primary Watchtower deployment builds Docker on EC2. This document preserves
the alternative GitHub Actions and ECR flow for a later phase.

## Flow

```text
Push to main
    -> GitHub unit tests
    -> Docker build
    -> mock container test
    -> immutable image in ECR
    -> EC2 pulls and runs that image
```

The workflow is `.github/workflows/publish-ecr.yml`.

## AWS prerequisites

Create:

- Private ECR repository `watchtower` in `ap-south-1`
- GitHub OIDC provider for `https://token.actions.githubusercontent.com`
- IAM role `WatchtowerGitHubEcrPublisher`
- GitHub repository variable `AWS_PUBLISH_ROLE_ARN`

The publisher role needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:ap-south-1:AWS_ACCOUNT_ID:repository/watchtower"
    }
  ]
}
```

The role trust policy should restrict access to the exact GitHub organization,
repository, and `main` branch.

## Publish

ECR publishing is intentionally manual while EC2 local builds are the primary
deployment. Start it through:

```text
GitHub > Actions > Publish Watchtower Image > Run workflow
```

Successful images use immutable commit/run tags.

## EC2 permissions

Attach an EC2 IAM role containing:

```text
AmazonEC2ContainerRegistryReadOnly
```

Do not configure permanent AWS access keys on EC2.

Install AWS CLI v2 on an x86_64 Ubuntu instance:

```bash
sudo apt-get update
sudo apt-get install -y curl unzip
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip \
  -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
sudo /tmp/aws/install
```

Verify the role:

```bash
aws sts get-caller-identity
```

## Test and deploy an ECR image

The EC2 bootstrap installs a separate `watchtower-ecr` command.

Test the newest ECR image:

```bash
watchtower-ecr mock
```

Deploy it:

```bash
watchtower-ecr deploy
watchtower logs
```

Deploy a specific immutable image for rollback:

```bash
watchtower-ecr deploy \
  AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/watchtower@sha256:DIGEST
```

The default `watchtower` command never contacts ECR. It always uses the image
built locally on EC2.
