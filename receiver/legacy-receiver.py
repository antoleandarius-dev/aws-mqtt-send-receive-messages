# receiver.py
import json
import paho.mqtt.client as mqtt
import sys
import os
import time
import yaml
import ssl


home_directory = os.path.expanduser("~")
# Path to Greengrass nucleus configuration
GG_CONFIG_PATH = f"{home_directory}/greengrass/v2/config.yaml"

# for testing
current_dir = os.path.dirname(os.path.realpath(__file__))
cert_path = os.path.join(current_dir, "certs")
GG_CONFIG_PATH = f"{cert_path}/config.yaml"

def load_config():
    """Load endpoint, certs, and thing name from config.yaml"""
    with open(GG_CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    # gets certificateFilePath, privateKeyPath, rootCaPath, thingName
    system_config = config.get("system", {})

    # gets region, iotDataEndpoint
    service_config = config.get("services", {}).get('aws.greengrass.Nucleus', {}).get('configuration', {})

    # fallback in case structure varies
    endpoint = service_config.get("iotDataEndpoint", '')
    thing_name = system_config.get("thingName")
    cert_path = system_config.get("privateKeyPath", "/greengrass/v2/device/private.pem.key")
    key_path = system_config.get("certificateFilePath", "/greengrass/v2/device/device.pem.crt")
    root_ca = system_config.get("rootCaPath", "/greengrass/v2/device/AmazonRootCA1.pem")

    return endpoint, thing_name, cert_path, key_path, root_ca

def main():
    # Load Greengrass config values
    PORT = 8883
    AWS_IOT_ENDPOINT, DEVICE_ID, cert_path, key_path, root_ca = load_config()
    TOPIC = f"devices/{DEVICE_ID}/commands"

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected successfully")
            client.subscribe(TOPIC)
            print(f"[{DEVICE_ID}] Subscribed to topic: {TOPIC}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_message(client, userdata, msg):
        print('message has arrived')
        payload = json.loads(msg.payload.decode())
        print(f"[{DEVICE_ID}] Message received: {payload}")

    print('AWS_IOT_ENDPOINT', AWS_IOT_ENDPOINT)
    client = mqtt.Client(client_id=DEVICE_ID)
    client.tls_set(
        ca_certs=root_ca,
        certfile=key_path,
        keyfile=cert_path,
        tls_version=ssl.PROTOCOL_TLSv1_2
    )

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(AWS_IOT_ENDPOINT, PORT)
    client.loop_forever()

if __name__ == "__main__":
    main()
