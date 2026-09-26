import base64
import hmac
import json
import os
import re
import urllib.request
import zlib
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import boto3

sns = boto3.client("sns")
secrets = boto3.client("secretsmanager")

SHARED_SECRET = secrets.get_secret_value(SecretId=os.environ["SECRET_ID"])["SecretString"]

FETCH_TIMEOUT_SECONDS = 4
MAX_PAGE_BYTES = 1_000_000


class _PageParser(HTMLParser):
    """Collects <title>, og:* meta tags, the first <h1>, <main> text and script srcs."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.og = {}
        self.h1 = ""
        self.main_text = []
        self.scripts = []
        self._open = set()
        self._h1_done = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("title", "h1", "main", "script", "style"):
            self._open.add(tag)
        if tag == "meta" and (attrs.get("property") or "").startswith("og:"):
            self.og[attrs["property"][3:]] = attrs.get("content") or ""
        elif tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        elif tag == "br" and "h1" in self._open:
            self.h1 += " "

    def handle_endtag(self, tag):
        self._open.discard(tag)
        if tag == "h1" and self.h1.strip():
            self._h1_done = True

    def handle_data(self, data):
        if "title" in self._open:
            self.title += data
        if "h1" in self._open and not self._h1_done:
            self.h1 += data
        if "main" in self._open and not self._open & {"script", "style"}:
            self.main_text.append(data)


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "blog-notify/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        data = resp.read(MAX_PAGE_BYTES)
        # Some CDNs gzip even when we don't ask for it.
        if resp.headers.get("Content-Encoding") == "gzip":
            data = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data, MAX_PAGE_BYTES)
        return data.decode(charset, errors="replace")


def _parse(html):
    parser = _PageParser()
    parser.feed(html)
    return parser


def _clean(text):
    return " ".join(text.split())


def _same_page(a, b):
    return urlparse(a).path.rstrip("/") == urlparse(b).path.rstrip("/")


def _article_from_spa_chunk(url, page):
    """
    Single-page apps (like chris-messer.com) serve the same HTML shell for every
    URL. On that site each post is a lazy-loaded JS chunk named after the slug
    (build-dumb-things -> BuildDumbThings-<hash>.js) whose article is an HTML
    template string, so find that chunk and parse the HTML inside it.
    """
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    chunk_prefix = "".join(part.capitalize() for part in slug.split("-")) + "-"
    if chunk_prefix == "-":
        return None

    for src in page.scripts:
        bundle_url = urljoin(url, src)
        bundle = _fetch(bundle_url)
        for chunk in re.findall(r'import\("\./([\w.-]+\.js)"\)', bundle):
            if chunk.startswith(chunk_prefix):
                js = _fetch(urljoin(bundle_url, chunk))
                template = re.search(r"=`(.*?)`", js, re.S)
                return _parse(template.group(1)) if template else None
    return None


def fetch_page_metadata(url):
    """Fetch a page and return what we can learn about it. Never raises."""
    if not url.startswith(("http://", "https://")):
        return {}

    try:
        page = _parse(_fetch(url))
        og = page.og
        title = og.get("title") or _clean(page.title)

        # The page's own tags describe some other page (usually the site root),
        # so they're a generic shell; look for the real article instead.
        if og.get("url") and not _same_page(og["url"], url):
            og, title = {}, ""
            article = _article_from_spa_chunk(url, page)
            if article:
                page, title = article, _clean(article.h1)
    except Exception as e:
        print(f"could not fetch metadata for {url}: {e}")
        return {}

    return {
        "title": title,
        "description": og.get("description", ""),
        "image": og.get("image", ""),
        "site_name": og.get("site_name", ""),
        "content": _clean(" ".join(page.main_text)),
    }


def handler(event, context):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-webhook-secret", "").encode(), SHARED_SECRET.encode()):
        return {"statusCode": 401, "body": "unauthorized"}

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw)

    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"statusCode": 400, "body": "invalid json"}

    if not isinstance(body, dict):
        return {"statusCode": 400, "body": "invalid json"}

    url = body.get("url", "")
    metadata = fetch_page_metadata(url) if url and not body.get("title") else {}
    title = body.get("title") or metadata.get("title") or "New post"

    sns.publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject="New blog post!",
        Message=f"{title}\n{url}"
    )

    return {"statusCode": 200, "body": "ok"}
