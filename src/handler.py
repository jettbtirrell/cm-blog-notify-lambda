import hmac
import json
import os
import boto3

sns = boto3.client("sns")
secrets = boto3.client("secretsmanager")

SHARED_SECRET = secrets.get_secret_value(SecretId=os.environ["SECRET_ID"])["SecretString"]


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-webhook-secret", "").encode(), SHARED_SECRET.encode()):
        return {"statusCode": 401, "body": "unauthorized"}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "invalid json"}

    title = body.get("title", "New post")
    url = body.get("url", "")

    sns.publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject="New blog post!",
        Message=f"{title}\n{url}"
    )

    return {"statusCode": 200, "body": "ok"}