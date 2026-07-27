# S3 Pre-signed URL Proxy - System Architecture

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LOCAL DEVELOPMENT ENVIRONMENT                   │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐         ┌──────────────┐
│                  │         │                  │         │              │
│     Request      │  HTTP   │      Flask       │  HTTPS  │      AWS     │
│   (Port: 8080)   │ Request │  Proxy Service   │ Request │   S3 Bucket  │
│                  ├────────►│   (Port: 8087)   ├────────►│              │
│                  │         │ Docker Container │         │              │
└──────────────────┘         └──────────────────┘         └──────────────┘
                                      │                           │
                                      │                           │
                                      │  HTTP 302 Redirect        │
                                      │  (Pre-signed URL)         │
                                      │                           │
                                      ▼                           ▼
                            ┌─────────────────┐         ┌──────────────┐
                            │                 │         │              │
                            │  Web Browser    │  HTTPS  │     AWS      │
                            │    /Client      ├────────►│   S3 Bucket  │
                            │                 │ Direct  │              │
                            └─────────────────┘ Access  └──────────────┘
```

## Request Flow

### 1. Application Creates Request
```
URL: http://localhost:8087/?objectkey=files/doc.pdf
```

### 2. Flask Proxy Service Processes
- Reads the object key from the query param named by `OBJECT_KEY_PARAM` (default `objectkey`)
- Validates that every param in `REQUIRED_PARAMS` is present (default `objectkey`)
- Generates S3 pre-signed URL using AWS boto3
- Creates URL with 240 minute validity

> Extra required params (e.g. `tenant`) can be enforced by listing them in `REQUIRED_PARAMS`
> (e.g. `REQUIRED_PARAMS=tenant,objectkey`). They are validated and logged but do not affect
> bucket or key selection.

### 3. HTTP 302 Redirect Response
```
HTTP/1.1 302 Found
Location: https://your-bucket.s3.us-east-1.amazonaws.com/files/doc.pdf?
          X-Amz-Algorithm=AWS4-HMAC-SHA256&
          X-Amz-Credential=AKIA...&
          X-Amz-Date=20241219T103045Z&
          X-Amz-Expires=14400&
          X-Amz-SignedHeaders=host&
          X-Amz-Signature=...
```

### 4. Client Downloads Directly from S3
Browser or HTTP client follows the redirect URL and downloads the file directly from S3.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Request from Application                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GET http://localhost:8087/                                         │
│      ?objectkey=attachments/2024/12/file.pdf                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: Flask Proxy Processing                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Extract object key from OBJECT_KEY_PARAM (default objectkey)    │
│     - objectkey: "attachments/2024/12/file.pdf"                     │
│                                                                     │
│  2. Validate every param listed in REQUIRED_PARAMS                  │
│     (default: objectkey)                                            │
│                                                                     │
│  3. Call AWS S3 boto3                                               │
│     s3_client.generate_presigned_url(                               │
│         'get_object',                                               │
│         Params={                                                    │
│             'Bucket': AWS_BUCKET,                                   │
│             'Key': 'attachments/2024/12/file.pdf'                   │
│         },                                                          │
│         ExpiresIn=14400  # 240 minutes                              │
│     )                                                               │
│                                                                     │
│  4. Log the request                                                 │
│     [INFO] key=... url_generated=True                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: HTTP 302 Redirect Response                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  HTTP/1.1 302 Found                                                 │
│  Location: https://your-bucket.s3.us-east-1.amazonaws.com/...       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: Client Follows Redirect                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GET https://your-bucket.s3.us-east-1.amazonaws.com/...             │
│                                                                     │
│  → Direct download from S3                                          │
│  → No proxy involved in file transfer                               │
│  → Fast and efficient                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Error Scenarios

### Missing Parameter
```
Request:  GET http://localhost:8087/?something=acme
Response: 400 Bad Request
Body:     {"error": "Missing required parameter: objectkey"}
```

A request carrying *some* of the proxy's params is malformed and gets the 400 above.
A request carrying *none* of them is not addressed to this proxy at all: with
PASSTHROUGH_PORT set it is handed to the app sharing the hostname (307), otherwise it
gets the same 400.

### Passthrough
```
Request:  GET http://localhost:8087/download/file?id=xxx-yyy-zzz
Response: 307 Temporary Redirect
Location: http://localhost:8088/download/file?id=xxx-yyy-zzz
```

The target host comes from the request's own `Host` header and must be covered by
`PASSTHROUGH_HOSTS` — an entry matches that host or any subdomain of it, and a bare `*`
matches anything. An uncovered host gets a 400; a `PASSTHROUGH_PORT` equal to the port
the request arrived on gets a 500 instead of looping back on itself.

### Invalid S3 Key
```
Request:  GET http://localhost:8087/?objectkey=nonexistent.pdf
Response: 500 Internal Server Error
Body:     {"error": "Failed to generate S3 URL", "details": "..."}
```

### AWS Credentials Error
```
Request:  GET http://localhost:8087/?objectkey=file.pdf
Response: 500 Internal Server Error
Body:     {"error": "Internal server error", "details": "..."}
Log:      [ERROR] AWS Error: ... error_code=InvalidAccessKeyId
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Docker Host                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Docker Container: s3-presigned-url-proxy                 │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────┐      │  │
│  │  │ Python 3.11 Runtime                             │      │  │
│  │  ├─────────────────────────────────────────────────┤      │  │
│  │  │                                                 │      │  │
│  │  │  Flask App (app.py)                             │      │  │
│  │  │  ├─ Flask 3.1.3                                 │      │  │
│  │  │  ├─ boto3 1.43.56                               │      │  │
│  │  │  └─ Listens on 0.0.0.0:8088                     │      │  │
│  │  │                                                 │      │  │
│  │  └─────────────────────────────────────────────────┘      │  │
│  │                                                           │  │
│  │  Environment Variables configured via docker-compose      │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                          ↓                                      │
│                   Port Mapping: 8087:8088                       │
│                          ↓                                      │
└──────────────────────────┼──────────────────────────────────────┘
                           ↓
                    localhost:8087
```

## Network Structure

```
┌────────────────────────────────────────────────────────────────────┐
│  Local Machine                                                     │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  127.0.0.1 (localhost)                                             │
│  ├─ Port 8080: Application                                         │
│  └─ Port 8087: Flask Proxy Service (Docker)                        │
│                                                                    │
│  Optional DNS Override:                                            │
│  /etc/hosts (Linux/Mac) or C:\Windows\System32\drivers\etc\hosts   │
│  → 127.0.0.1 s3proxy.local                                         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                               │
                               │ Internet
                               ↓
┌────────────────────────────────────────────────────────────────────┐
│  AWS Cloud                                                         │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  S3 Bucket (configured via environment variables)                  │
│  └─ Pre-signed URLs with time expiration                           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Sequence Diagram

```
Application       Flask Proxy         AWS S3            Browser/Client
   │                  │                  │                     │
   │ 1. GET Request   │                  │                     │
   ├─────────────────►│                  │                     │
   │ ?objectkey=Y     │                  │                     │
   │                  │                  │                     │
   │                  │                  │                     │
   │                  │ 2. Generate      │                     │
   │                  │    Pre-signed URL│                     │
   │                  ├─────────────────►│                     │
   │                  │                  │                     │
   │                  │ 3. Return URL    │                     │
   │                  │◄─────────────────┤                     │
   │                  │                  │                     │
   │ 4. HTTP 302      │                  │                     │
   │    Redirect      │                  │                     │
   │◄─────────────────┤                  │                     │
   │ Location: S3 URL │                  │                     │
   │                  │                  │                     │
   │ 5. Pass URL      │                  │                     │
   ├──────────────────┼──────────────────┼────────────────────►│
   │                  │                  │                     │
   │                  │                  │ 6. GET File         │
   │                  │                  │◄────────────────────┤
   │                  │                  │                     │
   │                  │                  │ 7. Return File      │
   │                  │                  ├────────────────────►│
   │                  │                  │                     │
```

## Security Layers

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 1: Network Isolation                                         │
├────────────────────────────────────────────────────────────────────┤
│ ✓ Docker container in bridge network                               │
│ ✓ Only port 8087 exposed to host                                   │
│ ✓ No external access (localhost only)                              │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Layer 2: Application Security                                      │
├────────────────────────────────────────────────────────────────────┤
│ ✓ Input validation (required parameters)                           │
│ ✓ Passthrough target host allowlist (PASSTHROUGH_HOSTS)            │
│ ✓ Error handling (no sensitive data in errors)                     │
│ ✓ Logging without credentials                                      │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Layer 3: AWS Security                                              │
├────────────────────────────────────────────────────────────────────┤
│ ✓ IAM credentials with minimal permissions                         │
│ ✓ Pre-signed URLs with time expiration (240 min)                   │
│ ✓ Bucket-level access control                                      │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Layer 4: Environment Isolation                                     │
├────────────────────────────────────────────────────────────────────┤
│ ⚠ LOCAL DEVELOPMENT ONLY                                           │
│ ⚠ Not for production use                                           │
│ ⚠ Configure credentials via environment variables                  │
└────────────────────────────────────────────────────────────────────┘
```

## Performance Characteristics

- **Response Time:** < 100ms (URL generation only)
- **File Transfer:** Direct S3 → Client (no proxy bottleneck)
- **Concurrent Requests:** Limited by Flask (single-threaded by default)
- **Memory Usage:** ~50-100 MB (Python + Flask + boto3)
- **CPU Usage:** Minimal (only URL generation)

## Monitoring & Logging

```
Log Level         Message Type              Example
─────────────────────────────────────────────────────────────────
INFO              Successful requests       key=Y url_generated=True
INFO              Passthrough (path only)   Passthrough: path=/download/file -> port 8088
WARNING           Missing parameters        Missing required parameter: objectkey
WARNING           Host not in allowlist     Passthrough refused: host=... not covered by ...
ERROR             AWS errors                AWS Error: error_code=NoSuchKey
ERROR             Unexpected errors         Unexpected error: exception=...
```

---

**Note:** These diagrams show the system architecture. For the actual implementation, refer to the code files.

