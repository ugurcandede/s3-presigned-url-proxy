# S3 Pre-signed URL Proxy - System Architecture

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LOCAL DEVELOPMENT ENVIRONMENT                    │
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
URL: http://localhost:8087/?tenant=mycompany&objectkey=files/doc.pdf
```

### 2. Flask Proxy Service Processes
- Parses query parameters (tenant, objectkey)
- Generates S3 pre-signed URL using AWS boto3
- Creates URL with 240 minute validity

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
│ STEP 1: Request from Application                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GET http://localhost:8087/                                         │
│      ?tenant=mycompany                                              │
│      &objectkey=attachments/2024/12/file.pdf                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: Flask Proxy Processing                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Extract parameters                                              │
│     - tenant: "mycompany"                                           │
│     - objectkey: "attachments/2024/12/file.pdf"                     │
│                                                                     │
│  2. Validate parameters (both required)                             │
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
│     [INFO] tenant=mycompany objectkey=... url_generated=True        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: HTTP 302 Redirect Response                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  HTTP/1.1 302 Found                                                 │
│  Location: https://your-bucket.s3.us-east-1.amazonaws.com/...      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: Client Follows Redirect                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  GET https://your-bucket.s3.us-east-1.amazonaws.com/...            │
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
Request:  GET http://localhost:8087/?tenant=mycompany
Response: 400 Bad Request
Body:     {"error": "Missing required parameter: objectkey"}
```

### Invalid S3 Key
```
Request:  GET http://localhost:8087/?tenant=x&objectkey=nonexistent.pdf
Response: 500 Internal Server Error
Body:     {"error": "Failed to generate S3 URL", "details": "..."}
```

### AWS Credentials Error
```
Request:  GET http://localhost:8087/?tenant=x&objectkey=file.pdf
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
│  │  Docker Container: grispi-url-proxy                       │  │
│  ├───────────────────────────────────────────────────────────┤  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────┐      │  │
│  │  │ Python 3.11 Runtime                             │      │  │
│  │  ├─────────────────────────────────────────────────┤      │  │
│  │  │                                                 │      │  │
│  │  │  Flask App (app.py)                             │      │  │
│  │  │  ├─ Flask 3.0.0                                 │      │  │
│  │  │  ├─ boto3 1.34.0                                │      │  │
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
│  → 127.0.0.1 usercontent.grispi.local                              │
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
   │ ?tenant=X        │                  │                     │
   │ &objectkey=Y     │                  │                     │
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
INFO              Successful requests       tenant=X objectkey=Y url_generated=True
WARNING           Missing parameters        Missing 'tenant' parameter
ERROR             AWS errors                AWS Error: error_code=NoSuchKey
ERROR             Unexpected errors         Unexpected error: exception=...
```

---

**Not:** Bu diyagramlar sistem mimarisini göstermektedir. Gerçek implementasyon için kod dosyalarına bakınız.

