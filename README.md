# S3 Pre-signed URL Proxy

[![Build](https://github.com/ugurcandede/s3-presigned-url-proxy/actions/workflows/build.yml/badge.svg)](https://github.com/ugurcandede/s3-presigned-url-proxy/actions/workflows/build.yml)
[![Docker Hub Publish](https://github.com/ugurcandede/s3-presigned-url-proxy/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/ugurcandede/s3-presigned-url-proxy/actions/workflows/docker-publish.yml)
[![Docker Hub](https://img.shields.io/docker/v/ugurcandede/s3-presigned-url-proxy?label=Docker%20Hub)](https://hub.docker.com/r/ugurcandede/s3-presigned-url-proxy)
[![Docker Image Size](https://img.shields.io/docker/image-size/ugurcandede/s3-presigned-url-proxy/latest)](https://hub.docker.com/r/ugurcandede/s3-presigned-url-proxy)

⚠️ **LOCAL DEVELOPMENT ONLY - NOT FOR PRODUCTION USE** ⚠️

A lightweight Python Flask service that proxies HTTP requests to AWS S3 pre-signed URLs with automatic 302 redirects. Perfect for local development environments where you need quick access to S3-stored files without implementing full AWS SDK integration.

## Overview

This service intercepts HTTP requests and converts them to time-limited AWS S3 pre-signed URLs. Simply pass the S3 object key as a query parameter, and get a secure, temporary URL that expires after 4 hours (configurable).

**URL Format:** `http://localhost:8087/?tenant=TENANT_ID&objectkey=OBJECT_KEY`

**Use Cases:**
- Local development environments
- Quick prototyping with S3-stored files
- Testing file access without complex AWS integration
- Development servers that need temporary S3 access

## Features

- 🚀 **Simple & Fast** - Single Flask container, < 100ms response time
- 🔄 **Automatic Redirects** - HTTP 302 to S3 pre-signed URLs
- 🐳 **Fully Containerized** - Docker Compose for easy deployment
- 📝 **Comprehensive Logging** - Track all requests and errors
- ✅ **Health Check** - Built-in `/health` endpoint with automatic Docker health monitoring
- 🔐 **Secure** - Pre-signed URLs with 4-hour expiration, read-only filesystem
- 🌐 **Platform Independent** - Works on Windows, Linux, and macOS
- 🛡️ **Hardened Security** - Read-only container filesystem with tmpfs for temporary files

## Quick Start

### Prerequisites

- Docker & Docker Compose installed
- AWS S3 bucket access credentials

### Option A: Using Docker Hub (Recommended)

Pull the pre-built image from Docker Hub:

```bash
docker pull ugurcandede/s3-presigned-url-proxy:latest
```

Then use the provided `docker-compose.example.yml` or create your own `docker-compose.yml`:

```yaml
# Option 1: Use the example file directly
docker-compose -f docker-compose.example.yml up -d

# Option 2: Copy and customize
cp docker-compose.example.yml docker-compose.yml
# Edit docker-compose.yml with your AWS credentials
nano docker-compose.yml  # or use your preferred editor

# Then start the service
docker-compose up -d
```
> Note: Make sure to update the AWS credentials in the compose file before starting the service.

### Option B: Build from Source

### 1. Clone and Setup

```bash
git clone https://github.com/ugurcandede/s3-presigned-url-proxy.git
cd s3-presigned-url-proxy
```

### 2. Configure Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` and set your AWS credentials:

```env
AWS_REGION=us-east-1
AWS_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
PRESIGNED_URL_EXPIRATION=14400
```

**Note:** Never commit the `.env` file to version control!

### 3. Start the Service

```bash
docker-compose up -d
```

### 3. Verify

```bash
curl http://localhost:8087/health
```

Expected response:
```json
{"status":"ok"}
```

### 4. Test with a Request

```bash
curl -I "http://localhost:8087/?tenant=test&objectkey=files/document.pdf"
```

Expected: HTTP 302 redirect to AWS S3 pre-signed URL

## Usage

### URL Structure

```
http://localhost:8087/?tenant=TENANT_ID&objectkey=OBJECT_KEY
```

**Parameters:**
- `tenant` (required) - Tenant identifier
- `objectkey` (required) - S3 object key (file path in bucket)

### Example Request

```bash
# Using curl
curl -I "http://localhost:8087/?tenant=mycompany&objectkey=attachments/2024/12/report.pdf"

# Response
HTTP/1.1 302 FOUND
Location: https://your-bucket.s3.amazonaws.com/attachments/2024/12/report.pdf?...
```

### Integration in Your Application

**Java/Spring Boot:**
```yaml
# application-dev.yml
user-content:
  base-url: http://localhost:8087/
```

**Node.js/Express:**
```javascript
const userContentBaseUrl = 'http://localhost:8087/';
const url = `${userContentBaseUrl}?tenant=${tenantId}&objectkey=${objectKey}`;
```

**Python:**
```python
USER_CONTENT_BASE_URL = 'http://localhost:8087/'
url = f'{USER_CONTENT_BASE_URL}?tenant={tenant_id}&objectkey={object_key}'
```

## API Endpoints

### `GET /health`

Health check endpoint to verify service status.

**Response:**
```json
{"status":"ok"}
```

### `GET /?tenant=X&objectkey=Y`

Main proxy endpoint that generates S3 pre-signed URL and returns 302 redirect.

**Success Response:**
- Status: `302 Found`
- Header: `Location: https://...s3.amazonaws.com/...`

**Error Responses:**

Missing parameter:
```json
{
  "error": "Missing required parameter: tenant"
}
```

AWS/S3 error:
```json
{
  "error": "Failed to generate S3 URL",
  "details": "Error message"
}
```

## Architecture

### Simple Single-Container Design

```
Application → http://localhost:8087/?tenant=X&objectkey=Y
           ↓
    Docker Container (Flask App)
    - Port 8088 internal
    - Port mapping: 8087:8088
           ↓
    AWS S3 Pre-signed URL Generation
           ↓
    HTTP 302 Redirect
           ↓
    Browser/Client → Direct S3 Download
```

### Port Configuration

- **Host Port:** 8087 (external access)
- **Container Port:** 8088 (Flask internal)
- **Why 8087?** Port 8088 was already in use on the development machine

For detailed architecture diagrams, see [ARCHITECTURE.md](ARCHITECTURE.md)

## Docker Commands

```bash
# Start service
docker-compose up -d

# Stop service
docker-compose down

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Restart service
docker-compose restart

# Rebuild after code changes
docker-compose up -d --build
```

## Configuration

All configuration is done via environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | - | AWS region (e.g., `us-east-1`) |
| `AWS_BUCKET` | - | S3 bucket name |
| `AWS_ACCESS_KEY_ID` | - | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | - | AWS secret key |
| `PRESIGNED_URL_EXPIRATION` | `14400` | URL validity in seconds (4 hours) |

### Docker Resource Limits

The container has the following resource constraints for optimal performance:

- **CPU Limit:** 0.25 cores (25% of one CPU)
- **Memory Limit:** 256 MB maximum
- **Memory Reservation:** 128 MB guaranteed minimum
- **Read-Only Filesystem:** Yes (with tmpfs for /tmp and /run)
- **Security:** `no-new-privileges` enabled

### Health Check Configuration

The container includes automatic health monitoring:

- **Check Interval:** Every 30 seconds
- **Timeout:** 10 seconds per check
- **Retries:** 3 failed checks before marking unhealthy
- **Start Period:** 40 seconds grace period on startup
- **Method:** Python urllib health endpoint test

View health status: `docker ps` (shows "healthy" or "unhealthy")

## Logging

The service logs all requests with the following format:

```
[TIMESTAMP] [LEVEL] message
```

**Example logs:**
```
[2024-12-19 10:30:45] [INFO] Incoming request: tenant=test objectkey=file.pdf path=
[2024-12-19 10:30:45] [INFO] tenant=test objectkey=file.pdf url_generated=True
[2024-12-19 10:30:45] [INFO] 172.25.0.1 - - [19/Dec/2024 10:30:45] "GET /?tenant=test&objectkey=file.pdf HTTP/1.1" 302 -
```

## Troubleshooting

### Service won't start

1. Check if Docker is running:
   ```bash
   docker ps
   ```

2. Check logs for errors:
   ```bash
   docker-compose logs
   ```

3. Verify port 8087 is not in use:
   ```bash
   # Linux/Mac
   lsof -i :8087
   
   # Windows
   netstat -ano | findstr :8087
   ```

### "Connection refused" error

- Ensure the container is running: `docker-compose ps`
- Restart the service: `docker-compose restart`
- Check firewall settings

### AWS credentials error

- Verify credentials in `docker-compose.yml`
- Ensure IAM user has `s3:GetObject` permission
- Check logs: `docker-compose logs s3-presigned-url-proxy`

### Files not found in S3

- Verify the `objectkey` matches the actual S3 file path
- Check S3 bucket permissions
- Test with AWS CLI: `aws s3 ls s3://your-bucket/path/`

## Security Notes

⚠️ **IMPORTANT:**

- **LOCAL DEVELOPMENT ONLY** - Do not use in production/staging
- **Hardcoded Credentials** - For dev convenience only
- **No Authentication** - Service has no auth layer
- **No HTTPS** - Uses plain HTTP
- **Port Exposure** - Only expose to localhost, never to internet

**For Production:**
- Use AWS SDK directly in your application
- Implement proper authentication/authorization
- Use environment variables or secrets management
- Deploy behind HTTPS/TLS
- Use production WSGI server (not Flask dev server)

## Technical Details

- **Language:** Python 3.11
- **Framework:** Flask 3.0.0
- **AWS SDK:** boto3 1.34.0
- **Container Base:** python:3.11-slim
- **Port Mapping:** 8087 (host) → 8088 (container)
- **Pre-signed URL Expiration:** 14400 seconds (4 hours)
- **Memory Usage:** ~50-100 MB
- **Response Time:** < 100ms (URL generation only)

## Project Structure

```
s3-presigned-url-proxy/
├── app.py                        # Flask application
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker Compose configuration
├── docker-compose.example.yml   # Example configuration
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment variables
├── .gitignore                   # Git ignore rules
├── LICENSE                      # MIT License
├── ARCHITECTURE.md              # Detailed architecture diagrams
└── README.md                    # This file
```

## Testing

Use the included test script:

**Windows:**
```bash
test.bat
```

**Linux/Mac:**
```bash
# Health check
curl http://localhost:8087/health

# Proxy request (show headers)
curl -I "http://localhost:8087/?tenant=test&objectkey=test.pdf"

# Full redirect test
curl -L "http://localhost:8087/?tenant=test&objectkey=test.pdf"

# Error test (missing parameter)
curl "http://localhost:8087/?tenant=test"
```

## Optional: Custom Domain

If you want to use a custom domain instead of `localhost`:

**Linux/Mac:**
```bash
sudo sh -c 'echo "127.0.0.1 usercontent.grispi.local" >> /etc/hosts'
```

**Windows:**
Edit `C:\Windows\System32\drivers\etc\hosts` as administrator and add:
```
127.0.0.1 usercontent.grispi.local
```

Then access via: `http://usercontent.grispi.local:8087/`

## FAQ

**Q: Why port 8087 instead of 8088?**  
A: Port 8088 was already in use on the development machine.

**Q: How long are pre-signed URLs valid?**  
A: Default is 14400 seconds (4 hours). Configure via `PRESIGNED_URL_EXPIRATION`.

**Q: Can I use this in production?**  
A: No! This is for local development only. Use AWS SDK directly in production.

**Q: Does this work with multiple tenants?**  
A: Yes, the tenant parameter is logged but all tenants use the same S3 bucket.

**Q: What S3 permissions are needed?**  
A: Minimum required: `s3:GetObject` on the bucket.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md)
- For Docker Hub auto-deploy setup, see [DOCKER_HUB_SETUP.md](DOCKER_HUB_SETUP.md)
- For GitHub Actions workflows documentation, see [WORKFLOWS.md](WORKFLOWS.md)
