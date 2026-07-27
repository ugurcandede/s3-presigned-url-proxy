<div align="center">
  <img src="docs/assets/logo.svg" alt="s3-presigned-url-proxy" width="100" height="100">
  <h1>S3 Pre-signed URL Proxy</h1>
  <p><em>Point a URL at it, get a pre-signed S3 redirect back.</em></p>
  <p>A tiny, fully env-configurable Flask service that turns an HTTP request into an AWS S3 pre-signed URL and 302-redirects to it. One container, no AWS SDK wiring in your app.</p>
  <br>

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=flat-square&logo=flask&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![AWS S3](https://img.shields.io/badge/AWS-S3-FF9900?style=flat-square&logo=amazons3&logoColor=white)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

> ⚠️ **Local development only.** No auth, no HTTPS, runs the Flask dev server. Don't expose it to the internet — in production, call the AWS SDK from your app instead.

## What it solves

In local development you often need temporary access to files stored in S3 — previews, attachments, user content — without wiring the AWS SDK into every service and frontend. This proxy centralizes that: your app builds a plain URL with the object key, the proxy generates a time-limited S3 pre-signed URL, and returns a `302` so the client downloads straight from S3. The proxy never touches the file bytes.

Behavior is driven entirely by environment variables, so it isn't tied to any one project — name your key parameter, require whatever query params you want, point it at any bucket.

## Quick start

```bash
git clone https://github.com/ugurcandede/s3-presigned-url-proxy.git
cd s3-presigned-url-proxy
cp .env.example .env          # set AWS_BUCKET + credentials
docker-compose up -d
```

`docker-compose.yml` reads every value from `.env` — there is nothing else to edit.

### Without cloning (published image)

```bash
docker run -d -p 8087:8088 --env-file .env ugurcandede/s3-presigned-url-proxy:latest
```

### Verify

```bash
curl http://localhost:8087/health                          # {"status":"ok"}
curl -I "http://localhost:8087/?objectkey=files/doc.pdf"   # 302 -> https://...s3...
```

## Prerequisites

- **Docker & Docker Compose**, or **Python 3.11** to run from source.
- An **S3 bucket** and credentials with `s3:GetObject`.
- AWS credentials via any standard source: environment variables, `~/.aws/credentials`, SSO, or an IAM role. The service starts as long as the boto3 chain resolves credentials.

## Configuration

All configuration is via environment variables (see `.env.example`).

| Variable                   | Default     | Description                                                                                                       |
|----------------------------|-------------|-------------------------------------------------------------------------------------------------------------------|
| `AWS_BUCKET`               | —           | S3 bucket name (required)                                                                                         |
| `AWS_REGION`               | `us-east-1` | AWS region                                                                                                        |
| `AWS_ACCESS_KEY_ID`        | —           | Access key (optional if creds come from `~/.aws`/IAM role)                                                        |
| `AWS_SECRET_ACCESS_KEY`    | —           | Secret key (optional, as above)                                                                                   |
| `PRESIGNED_URL_EXPIRATION` | `14400`     | URL validity in seconds (4 hours)                                                                                 |
| `OBJECT_KEY_PARAM`         | `objectkey` | Which query param's value is used as the S3 object key                                                            |
| `REQUIRED_PARAMS`          | `objectkey` | Comma-separated query params that must be present                                                                 |
| `PASSTHROUGH_PORT`         | —           | If set, requests missing `REQUIRED_PARAMS` are redirected to the same URL on this port instead of returning `400` |
| `PROXY_HOST_PORT`          | `8087`      | Host port published by docker-compose (container always listens on 8088)                                          |

> `PROXY_HOST_PORT` is used only by `docker-compose.yml` to map the host port; it is not read by the app. Keep it off your other services' ports (e.g. a UI on `8088` → proxy on `8087`).

## Usage

```
GET http://localhost:8087/?objectkey=<S3_OBJECT_KEY>
```

The value of the `OBJECT_KEY_PARAM` query parameter is used as the S3 key. On success you get a `302` redirect to a pre-signed URL; the client follows it and downloads directly from S3.

```bash
curl -I "http://localhost:8087/?objectkey=attachments/2024/report.pdf"

HTTP/1.1 302 FOUND
Location: https://your-bucket.s3.amazonaws.com/attachments/2024/report.pdf?X-Amz-...
```

Drop-in from your app:

```javascript
// Node / Express
const url = `http://localhost:8087/?objectkey=${encodeURIComponent(objectKey)}`;
```

```python
# Python
url = f"http://localhost:8087/?objectkey={object_key}"
```

### Requiring additional parameters

`REQUIRED_PARAMS` lets a deployment enforce extra query params beyond the key. They are validated and logged, but do not affect the bucket or key — useful for tagging requests (e.g. a tenant id):

```bash
REQUIRED_PARAMS=tenant,objectkey
```

```bash
curl -I "http://localhost:8087/?tenant=acme&objectkey=files/doc.pdf"   # 302
curl -i  "http://localhost:8087/?objectkey=files/doc.pdf"              # 400 Missing required parameter: tenant
```

### Sharing a hostname with another app

If another service (e.g. a UI) answers on the same hostname but a different port, and links to it were accidentally built with the proxy's port, set `PASSTHROUGH_PORT` to that service's port. Requests missing `REQUIRED_PARAMS` are then bounced back to it — same scheme, host, path and query, only the port swapped:

```bash
PASSTHROUGH_PORT=8088
```

```bash
curl -I "http://localhost:8087/download/file?id=xxx-yyy-zzz"

HTTP/1.1 302 FOUND
Location: http://localhost:8088/download/file?id=xxx-yyy-zzz
```

The path is re-encoded from Werkzeug's parsed form, so a percent-encoded path separator (`%2F`) is normalized to `/`.

This is a workaround for a link-generation bug upstream, not a routing layer — fix the caller when you can.

## Endpoints

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/health` | `200 {"status":"ok"}` |
| `GET` | `/?objectkey=…` | `302` redirect to the pre-signed URL |

| Status | When |
|--------|------|
| `302` | Pre-signed URL generated — `Location` header points to S3 |
| `400` | A required query parameter is missing |
| `500` | AWS/S3 error or unexpected failure |

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — request flow, data flow, and deployment diagrams.

## Layout

```
s3-presigned-url-proxy/
├── app.py                       # Flask service (single file)
├── test_app.py                  # pytest suite
├── requirements.txt             # runtime deps (Flask, boto3)
├── requirements-dev.txt         # dev deps (+ pytest)
├── Dockerfile
├── docker-compose.yml           # reads values from .env
├── .env.example
├── ARCHITECTURE.md
├── docs/assets/logo.svg
└── README.md
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The suite stubs the AWS call, so no credentials or network are needed.

## Notes and limitations

- **Local development only** — no authentication, no HTTPS, Flask's dev server. Anyone who can reach the port can sign a URL for any key in the bucket.
- **Single bucket.** All requests resolve against `AWS_BUCKET`; there is no per-request bucket or tenant isolation.
- **Object key from a query param only** — there is no path-based key form.
- `PASSTHROUGH_PORT` builds its redirect from the request's `Host` header, so a client that spoofs `Host` gets redirected to that host — another reason not to expose this beyond localhost.
- The container runs hardened under Docker Compose (read-only filesystem with tmpfs, `no-new-privileges`, CPU/memory limits).
- The host port is `8087` (mapped to the container's `8088`); running from source listens on `8088` directly.

---


## License

MIT © Ugurcan Dede — see [LICENSE](LICENSE).

---

<p align="center">
   <a href="https://github.com/ugurcandede">
    <img src="https://img.shields.io/badge/Built%20with%20%E2%9D%A4%20by-@ugurcandede-181717?logo=github&logoColor=white" alt="Built with love by @ugurcandede">
  </a>
</p>

<p align="center">
    <sub>Not affiliated with Amazon Web Services. "AWS" and "Amazon S3" are trademarks of Amazon.com, Inc. or its affiliates.</sub>                       
</p>
