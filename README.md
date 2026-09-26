# cm-blog-notify-lambda

Sends an email (and eventually a text) when a new blog post is published.

A webhook hits a public Lambda function URL, the function checks a shared secret, then publishes to an SNS topic that emails subscribers.

## Calling it

The full request/response spec is in [`openapi.yaml`](openapi.yaml), with a sample payload in [`examples/notify-request.json`](examples/notify-request.json).

```bash
curl -X POST "<FUNCTION_URL>" \
  -H "Content-Type: application/json" \
  -H "x-webhook-secret: <SECRET>" \
  -d @examples/notify-request.json
```

| Response | Meaning |
| --- | --- |
| `200 ok` | Notification sent |
| `401 unauthorized` | Missing or wrong secret |
| `400 invalid json` | Body isn't valid JSON |

## Project layout

- `src/handler.py` – the Lambda function
- `template.yaml` – CloudFormation for the function, URL, SNS topic and subscriptions
- `deploy/bootstrap.yaml` – one-time setup for the GitHub Actions deploy role (OIDC, no stored AWS keys)
- `.github/workflows/deploy.yml` – deploys on push to `main`

## Deploying

Push changes to `src/` or `template.yaml` on `main` and GitHub Actions deploys them.

The webhook secret lives in AWS Secrets Manager (`blog-notify/shared-secret`). The phone number and email are GitHub Actions secrets (`PHONE_NUMBER`, `EMAIL_ADDRESS`).

## Notes

- New email subscribers have to click the AWS confirmation link before they get anything.
- SMS isn't working yet: the account needs a registered toll-free number to text US numbers.
