"""Refined AWS IoT Core sender with configurable logging and device targeting."""

import json
import logging
import time

import boto3


REGION = "us-east-1"
RECEIVER_DEVICES = ["Laptop-Core-1"]
LOG_LEVEL = "INFO"
IOT_ENDPOINT_OVERRIDE = None
ENABLE_BROADCAST = False
DEFAULT_QOS = 1
DEFAULT_BROADCAST_TOPIC = "devices/all/commands"


def configure_logging(level):
    """Set up logging with the requested verbosity level."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger("sender-final")


def describe_iot_endpoint(region, logger):
    """Fetch the ATS IoT data endpoint for the provided region."""
    try:
        client = boto3.client("iot", region_name=region)
        response = client.describe_endpoint(endpointType="iot:Data-ATS")
        endpoint = response.get("endpointAddress")
        if not endpoint:
            raise ValueError("iot:Data-ATS endpoint not returned by AWS")
        logger.debug("Resolved IoT endpoint %s for region %s", endpoint, region)
        return endpoint
    except Exception:
        logger.exception("Unable to resolve IoT endpoint for region %s", region)
        raise


def build_iotdata_client(region, endpoint, logger):
    """Create an IoT Data client using either a provided endpoint or a discovered one."""
    resolved_endpoint = endpoint or describe_iot_endpoint(region, logger)
    endpoint_url = f"https://{resolved_endpoint}"
    logger.debug("Instantiating IoT Data client for %s", endpoint_url)
    return boto3.client(
        "iot-data",
        region_name=region,
        endpoint_url=endpoint_url,
    )


def load_receiver_devices(device_list):
    """Validate and normalize the list of receiver device IDs."""
    return [device for device in device_list if device]


def publish_to_device(client, device_id, payload, qos, logger):
    """Publish a JSON payload to the commands topic of a single device."""
    topic = f"devices/{device_id}/commands"
    try:
        client.publish(topic=topic, qos=qos, payload=json.dumps(payload))
        logger.info("Published to %s: %s", topic, payload)
        return True
    except Exception:
        logger.exception("Failed to publish to %s", topic)
        return False


def broadcast_command(client, payload, qos, logger):
    """Publish a JSON payload to the broadcast commands topic."""
    try:
        client.publish(topic=DEFAULT_BROADCAST_TOPIC, qos=qos, payload=json.dumps(payload))
        logger.info("Broadcasted to %s: %s", DEFAULT_BROADCAST_TOPIC, payload)
        return True
    except Exception:
        logger.exception("Broadcast failed for topic %s", DEFAULT_BROADCAST_TOPIC)
        return False


def should_broadcast(flag):
    """Determine whether broadcast publishing is enabled."""
    return bool(flag)


def build_sample_payload():
    """Assemble the default payload used for demonstration runs."""

    # sample payload with no real action to perform
    return {
        "action": "start_detection",
        "config": {
            "camera_resolution": "1280x720",
            "detection_threshold": 0.5,
        },
    }

    #sample payload to handle file download and processing
    return {
        "action": 'update',
        "url": "https://antokf-testbucket.s3.us-east-1.amazonaws.com/hello_component_check.py?response-content-disposition=inline&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Security-Token=IQoJb3JpZ2luX2VjEA0aCXVzLWVhc3QtMSJIMEYCIQCukJ17W7iu54OCc%2B8%2FlD%2FlX%2F%2FKyRhuSDxpPyxlWo3D5wIhANyzX%2FkWg%2Bo3mSp8t2X%2B4e%2BeaBYrwhBq8YHhqWePXMGoKu8ECKb%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEQABoMODkxNjEyNTc5NzY2Igy8H%2FT6ncFDVF1enQ0qwwT%2F2Appk%2F%2B93lbhLss2Mc%2BE9vUPz2igQMvcjstK4lN0WkQLTS8iLYy7qC2dfaaFJnHr8sBISNMMWdbO6v44S4A%2FWOOJtbVoo8gC%2Facmyp91Gd6cJujOJjXVzQ2bQQzqKx0nj5GxGhgDQuOAlAMrzoQtTU7LgEym0ieGpOEmhl7sRpec6BaW07oB6YkiDodnGukkHsnSyzXQAgrYsIWDHls3r7LbREECEnAG482PmEBxSy9Xnw6pW1VlCuBH4OeNyAN70zHISkDnIvwJ4K2rhf5DP7TqVmOy9nJPeIFh14m5ndjA4Kz21FtVf7skn1GGPgq%2Fm6mp42rNsoR7zKMEWx1eJHySQorApeztxiRfoTityKdi7R2StdZfaMIeChgrjnF2GP779S%2B3%2FW9E5%2BFIup2GcU%2FbMq2d3a71ZEGWPIcHkW%2FBGNteUmHtneS0h5Uytn1TUQV8Sia2v%2Bkq6vZ1tj731SPVW9jB5vY81uxCBZwHsSqZomWFX%2B8U%2F331EmpWXPyfstaiWAUrc%2B2cKUYwPlwHDH5QW8uxq%2BuaxGoP48XPJR%2F0qQJjq%2BI%2FHLoj6mCppiqGrfghSydkZd7EHNEWJbpIrhlYByIfElWSLwZyIM%2FyuGifLsrFYmTuiwE1TeYb01%2Flk%2B5GfpMz3ifXkzIU%2FpSYawnsdCNjjZW0X75hzI8LKci6fp99cds40936FTbemJi9NWHmhRITkpJnRZTPv0u%2BW9bVdK7%2FodwjOKslJ2qaqgg0MJX7ARSlnHEDs2tdo2iPdDcwzpSUxwY6xAIDv4FTIzp4DcIe%2BAzHDu2aV1KnBdixJYwzAQbIwe7bqS9TiscCCWR%2FCZSdBrJfW3rP%2B3yY9rn7lUZsrc%2BvZnVKZWslh0kYCGCSjX6YDXHmzxE29e7OYWBj%2FQ7rpEHomudNv%2FLKb0UHPyAEqXVQFBKHrvhWEwwn0e59YrACK5hxLUHzjI0wC7bF6htO52nmDsH1hZn0zzhEpctTMM8BlTH9TbqZ%2FX8L0%2BnUSOfmdXPJlQPnFTukq0AHp5gVBIUBNPe5AD8ORXdrHVg0iB9hSYwilOdfQR6eMYdfw4o3%2BUUB2gzAC03OZiyQb%2FaVJHzksxUxcTltdvOW1TLdNHVMewQgUwulsoVUr3C2lmXeIp9vdkK5Q9w7ARQ8SU%2FlbzkATJuT2huTxkCAy5Vw4FIf6A8S%2FhVLHCiHYawLnjU45ubkKX6R0y4%3D&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=ASIA47GCAI63BIHFC5TN%2F20251007%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20251007T124211Z&X-Amz-Expires=7200&X-Amz-SignedHeaders=host&X-Amz-Signature=9cd298dba596ebd498c573b24e1bf2b91444cd12e54e352379b5010ccbfc9f03",
        "filename": "hello_component_check.py",
        "command": "python hello_component_check.py"
    }


def main():
    """Initialize clients, publish sample commands, and optionally broadcast."""
    logger = configure_logging(LOG_LEVEL)

    iotdata_client = build_iotdata_client(REGION, IOT_ENDPOINT_OVERRIDE, logger)
    receivers = load_receiver_devices(RECEIVER_DEVICES)
    payload = build_sample_payload()

    for device in receivers:
        publish_to_device(iotdata_client, device, payload, DEFAULT_QOS, logger)
        time.sleep(0.2)

    if should_broadcast(ENABLE_BROADCAST):
        broadcast_command(iotdata_client, payload, DEFAULT_QOS, logger)


if __name__ == "__main__":
    main()
