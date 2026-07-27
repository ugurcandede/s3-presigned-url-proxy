import os
import logging
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

app = Flask(__name__)

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
# When set, requests missing the required params are redirected to the same URL on
# this port instead of getting a 400 — for setups where another app shares the host
# and only attachment requests belong to this proxy. Unset = plain 400.
PASSTHROUGH_PORT = os.environ.get('PASSTHROUGH_PORT')

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


@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def proxy_url(path):
    """
    Main proxy endpoint that converts requests to S3 pre-signed URLs.

    The object key is read from the query parameter named by OBJECT_KEY_PARAM.
    Every parameter listed in REQUIRED_PARAMS must be present; others are accepted
    and logged but do not affect the generated URL.
    """
    # Log incoming request
    logger.info(f"Incoming request: params={dict(request.args)} path={path}")

    # Validate configured required parameters
    missing = [p for p in REQUIRED_PARAMS if not request.args.get(p)]
    if missing:
        if PASSTHROUGH_PORT:
            # Not an attachment request — hand it back to whatever runs on PASSTHROUGH_PORT,
            # same host, path and query, only the port swapped.
            query = request.query_string.decode()
            target = f"{request.scheme}://{request.host.split(':')[0]}:{PASSTHROUGH_PORT}{request.path}"
            if query:
                target += f"?{query}"
            logger.info(f"Passthrough: missing={missing} target={target}")
            return redirect(target, code=302)

        logger.warning(f"Missing required parameter: {missing[0]}")
        return jsonify({"error": f"Missing required parameter: {missing[0]}"}), 400

    object_key = request.args.get(OBJECT_KEY_PARAM)
    if not object_key:
        logger.warning(f"Missing object key parameter: {OBJECT_KEY_PARAM}")
        return jsonify({"error": f"Missing object key parameter: {OBJECT_KEY_PARAM}"}), 400

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

    logger.info(f"Starting Proxy Service on port 8088")
    logger.info(f"AWS Region: {AWS_REGION}, Bucket: {AWS_BUCKET}")
    logger.info(f"Required params: {REQUIRED_PARAMS}, Object key param: {OBJECT_KEY_PARAM}")
    logger.info(f"Passthrough port: {PASSTHROUGH_PORT or 'disabled (400 on missing params)'}")
    logger.info("⚠️  LOCAL DEVELOPMENT ONLY - DO NOT USE IN PRODUCTION ⚠️")

    app.run(host='0.0.0.0', port=8088, debug=False)

