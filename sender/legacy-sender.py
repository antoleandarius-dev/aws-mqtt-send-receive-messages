# sender.py
import boto3
import json
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AWS_REGION = "us-east-1"

# If you want, you can dynamically fetch IoT endpoint
iot_client = boto3.client('iot', region_name=AWS_REGION)
endpoint = iot_client.describe_endpoint(endpointType='iot:Data-ATS')['endpointAddress']

# Create iot-data client using discovered endpoint
iotdata = boto3.client("iot-data", region_name=AWS_REGION, endpoint_url=f"https://{endpoint}")

# List of receivers to send messages to
receiver_devices = ["Laptop-Core-1"]  # extend as needed

def publish_to_device(device_id, payload, qos=1):
    topic = f"devices/{device_id}/commands"
    try:
        iotdata.publish(topic=topic, qos=qos, payload=json.dumps(payload))
        logger.info("Published to %s: %s", topic, payload)
        return True
    except Exception:
        logger.exception("Publish failed for %s", topic)
        return False

def broadcast(payload, qos=1):
    topic = "devices/all/commands"
    try:
        iotdata.publish(topic=topic, qos=qos, payload=json.dumps(payload))
        logger.info("Broadcasted to %s: %s", topic, payload)
        return True
    except Exception:
        logger.exception("Broadcast failed")
        return False

if __name__ == "__main__":
    payload = {
        "action": "start_detection",
        "config": {"camera_resolution": "1280x720", "detection_threshold": 0.5}
    }

    # send individually
    for dev in receiver_devices:
        publish_to_device(dev, payload)
        time.sleep(0.2)

    # optional broadcast
    # broadcast(payload)