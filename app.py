import os
import logging
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, request, redirect, jsonify
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# static_folder=None: Flask's implicit /static route would otherwise shadow the
# catch-all and swallow a co-hosted app's asset requests. This app serves no files.
app = Flask(__name__, static_folder=None)

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
AWS_BUCKET = os.environ.get('AWS_BUCKET')
# Coerce empty strings (e.g. compose passing an undefined var) to None so boto3
# falls back to its credential chain (~/.aws, SSO, IAM role) instead of empty creds.
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID') or None
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY') or None
PRESIGNED_URL_EXPIRATION = int(os.environ.get('PRESIGNED_URL_EXPIRATION', '14400'))  # 240 minutes

# Request configuration
OBJECT_KEY_PARAM = os.environ.get('OBJECT_KEY_PARAM', 'objectkey')
REQUIRED_PARAMS = [p.strip() for p in os.environ.get('REQUIRED_PARAMS', 'objectkey').split(',') if p.strip()]
# Passthrough: for setups where another app shares this hostname on a different port.
# A request carrying none of this proxy's params is handed back to PASSTHROUGH_PORT
# instead of being rejected. PASSTHROUGH_HOSTS bounds which hosts may be redirected to,
# since the target is derived from the client-supplied Host header. An entry matches the
# host itself or any subdomain of it, so 'example.local' already covers every subdomain —
# write the bare host, not '*.example.local'. A bare '*' matches any host.
# Unset = feature off, plain 400.
PASSTHROUGH_PORT = os.environ.get('PASSTHROUGH_PORT') or None
PASSTHROUGH_HOSTS = [h for h in (e.strip().lower()
                                 for e in os.environ.get('PASSTHROUGH_HOSTS', '').split(',')) if h]
PASSTHROUGH_ANY_HOST = '*' in PASSTHROUGH_HOSTS

if PASSTHROUGH_PORT:
    if not (PASSTHROUGH_PORT.isdigit() and 1 <= int(PASSTHROUGH_PORT) <= 65535):
        raise ValueError(f"PASSTHROUGH_PORT must be a port number, got {PASSTHROUGH_PORT!r}")
    if not PASSTHROUGH_HOSTS:
        raise ValueError("PASSTHROUGH_PORT requires PASSTHROUGH_HOSTS (comma-separated hosts the redirect may target)")
    if PASSTHROUGH_ANY_HOST:
        logger.warning("PASSTHROUGH_HOSTS contains '*': any Host header will be redirected to. "
                       "That is an open redirect — list real hostnames instead outside local development.")

# Initialize S3 client
s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200


def passthrough():
    """
    Hand a request back to the app on PASSTHROUGH_PORT: same scheme, host, path and
    query, only the port swapped.

    The target is derived from request.url rather than request.path, because the latter
    has already been percent-decoded and re-inserting it would turn an encoded '#' or '?'
    into a live delimiter and truncate the redirect. 307 keeps the method and body intact.
    """
    parts = urlsplit(request.url)
    hostname = parts.hostname or ''

    if not PASSTHROUGH_ANY_HOST and not any(hostname == h or hostname.endswith(f".{h}") for h in PASSTHROUGH_HOSTS):
        logger.warning(f"Passthrough refused: host={hostname} not covered by PASSTHROUGH_HOSTS")
        return jsonify({"error": "Passthrough not allowed for this host"}), 400

    arrival_port = parts.port or (443 if parts.scheme == 'https' else 80)
    if str(arrival_port) == PASSTHROUGH_PORT:
        logger.error(f"PASSTHROUGH_PORT={PASSTHROUGH_PORT} is the port this request arrived on — refusing to redirect to self")
        return jsonify({"error": "Passthrough misconfigured: PASSTHROUGH_PORT is the port this request arrived on"}), 500

    # Bracket an IPv6 literal back up; urlsplit strips the brackets off .hostname.
    host = f"[{hostname}]" if ':' in hostname else hostname
    target = urlunsplit((parts.scheme, f"{host}:{PASSTHROUGH_PORT}", parts.path, parts.query, ''))

    # Path only: the query belongs to another app and may carry its secrets.
    logger.info(f"Passthrough: path={parts.path} -> port {PASSTHROUGH_PORT}")
    return redirect(target, code=307)


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def proxy_url(path):
    """
    Main proxy endpoint that converts requests to S3 pre-signed URLs.

    The object key is read from the query parameter named by OBJECT_KEY_PARAM.
    Every parameter listed in REQUIRED_PARAMS must be present; others are accepted
    and logged but do not affect the generated URL.

    A request carrying none of those params is not addressed to this proxy at all, so
    with PASSTHROUGH_PORT set it is handed to the app sharing this hostname. A request
    carrying some of them is a malformed proxy request and still gets its 400 — routing
    on "params absent" rather than "validation failed" keeps typos reportable.
    """
    our_params = REQUIRED_PARAMS + ([OBJECT_KEY_PARAM] if OBJECT_KEY_PARAM not in REQUIRED_PARAMS else [])

    if PASSTHROUGH_PORT and not any(request.args.get(p) for p in our_params):
        return passthrough()

    # Log incoming request
    logger.info(f"Incoming request: params={dict(request.args)} path={path}")

    # Validate configured required parameters
    missing = [p for p in our_params if not request.args.get(p)]
    if missing:
        logger.warning(f"Missing required parameter: {missing[0]}")
        return jsonify({"error": f"Missing required parameter: {missing[0]}"}), 400

    object_key = request.args.get(OBJECT_KEY_PARAM)

    try:
        # Generate S3 pre-signed URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': AWS_BUCKET,
                'Key': object_key
            },
            ExpiresIn=PRESIGNED_URL_EXPIRATION
        )

        logger.info(f"key={object_key} url_generated=True")

        # Return 302 redirect to the pre-signed URL
        return redirect(presigned_url, code=302)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"AWS Error: key={object_key} error_code={error_code} error_message={error_message}")
        return jsonify({
            "error": "Failed to generate S3 URL",
            "details": error_message
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error: key={object_key} exception={str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    # Verify AWS credentials are resolvable (env, ~/.aws config, or an IAM role)
    if boto3.Session().get_credentials() is None:
        logger.error("No AWS credentials found! Set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, configure ~/.aws, or run with an IAM role.")
        exit(1)

    # 8088 is what the container listens on; override when running from source next to
    # an app that already owns that port, otherwise the two silently fight over it.
    port = int(os.environ.get('PORT', '8088'))

    logger.info(f"Starting Proxy Service on port {port}")
    logger.info(f"AWS Region: {AWS_REGION}, Bucket: {AWS_BUCKET}")
    logger.info(f"Required params: {REQUIRED_PARAMS}, Object key param: {OBJECT_KEY_PARAM}")
    logger.info(f"Passthrough: {f'port {PASSTHROUGH_PORT}, hosts {PASSTHROUGH_HOSTS}' if PASSTHROUGH_PORT else 'disabled (400 on missing params)'}")
    logger.info("⚠️  LOCAL DEVELOPMENT ONLY - DO NOT USE IN PRODUCTION ⚠️")

    app.run(host='0.0.0.0', port=port, debug=False)

