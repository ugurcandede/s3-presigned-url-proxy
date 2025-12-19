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
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
PRESIGNED_URL_EXPIRATION = int(os.environ.get('PRESIGNED_URL_EXPIRATION', '14400'))  # 240 minutes

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
    Main proxy endpoint that converts local URLs to S3 pre-signed URLs
    """
    # Extract query parameters
    tenant = request.args.get('tenant')
    object_key = request.args.get('objectkey')

    # Log incoming request
    logger.info(f"Incoming request: tenant={tenant} objectkey={object_key} path={path}")

    # Validate required parameters
    if not tenant:
        logger.warning("Missing 'tenant' parameter")
        return jsonify({"error": "Missing required parameter: tenant"}), 400

    if not object_key:
        logger.warning("Missing 'objectkey' parameter")
        return jsonify({"error": "Missing required parameter: objectkey"}), 400

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

        logger.info(f"tenant={tenant} objectkey={object_key} url_generated=True")

        # Return 302 redirect to the pre-signed URL
        return redirect(presigned_url, code=302)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"AWS Error: tenant={tenant} objectkey={object_key} error_code={error_code} error_message={error_message}")
        return jsonify({
            "error": "Failed to generate S3 URL",
            "details": error_message
        }), 500

    except Exception as e:
        logger.error(f"Unexpected error: tenant={tenant} objectkey={object_key} exception={str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    # Verify AWS credentials are set
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        logger.error("AWS credentials not set! Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")
        exit(1)

    logger.info(f"Starting Grispi URL Proxy Service on port 8088")
    logger.info(f"AWS Region: {AWS_REGION}, Bucket: {AWS_BUCKET}")
    logger.info("⚠️  LOCAL DEVELOPMENT ONLY - DO NOT USE IN PRODUCTION ⚠️")

    app.run(host='0.0.0.0', port=8088, debug=False)

