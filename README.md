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

Both fields are optional. Just sending the link works too; the title is looked up from the page:

```bash
curl -X POST "<FUNCTION_URL>" \
  -H "Content-Type: application/json" \
  -H "x-webhook-secret: <SECRET>" \
  -d '{"url": "https://chris-messer.com/writing/build-dumb-things"}'
```

| Response | Meaning |
| --- | --- |
| `200 ok` | Notification sent |
| `401 unauthorized` | Missing or wrong secret |
| `400 invalid json` | Body isn't a valid JSON object |

## Title lookup

If `title` is missing or empty, the function fetches `url` and uses, in order:

1. The page's `og:title`, then its `<title>`
2. If those tags describe a different page (their `og:url` doesn't match), the page is a single-page-app shell, as on chris-messer.com. The function then finds the post's JS chunk by slug (`build-dumb-things` → `BuildDumbThings-*.js`) and uses the `<h1>` from the article HTML inside it.
3. `"New post"` if nothing works

Step 2 depends on how that site is built, so it may need updating if the site changes. The lookup also collects the article text, ready for storing later.

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
