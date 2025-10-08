# AWS MQTT Demo

Python reference implementation for publishing commands to AWS IoT Core and consuming them on a Greengrass device. It includes:

> Note: Receiver script requires the certificates and respective key, pem files (preferably a greengrass environment)

- `sender/sender.py` – publishes JSON commands to targeted devices (and optionally a broadcast topic).
- `receiver/receiver.py` – subscribes to device topics, logs messages, and processes an `update` action that can download and execute artifacts.
- Legacy scripts (`legacy-sender.py`, `legacy-receiver.py`) retained for comparison.

> The code base is meant for local experimentation. Review and harden before deploying in production.

---

## Repository Layout

- `sender/sender.py` – final publisher client without environment-variable dependencies.
- `sender/requirements.txt` – Python dependencies for the sender client.
- `receiver/receiver.py` – final MQTT receiver client with the `update` action workflow.
- `receiver/requirements.txt` – Python dependencies for the receiver client.
- `README.md` – this document.

---

## Prerequisites

1. **AWS account with IoT Core and Greengrass v2** provisioned.
2. **Device certificates and configuration**
   - Place `config.yaml`, `device.pem.crt`, `private.pem.key`, and `AmazonRootCA1.pem` inside the path referenced in your config.
3. **Python 3.9+** and virtual environment tooling.
4. **AWS credentials** readable by the environment running `sender.py` (for IoT endpoint discovery).

---

## Setup

```bash
cd aws-mqtt
python3 -m venv .venv
source .venv/bin/activate

# Receiver dependencies
pip install -r receiver/requirements.txt

# Sender dependencies (Boto3)
pip install -r sender-requirement.txt
```

If you plan to experiment with the legacy scripts, also install any additional requirement files as needed.

---

## Receiver Client

Path: `receiver/receiver.py`

### Configuration Resolution

The client attempts to load Greengrass configuration in the following order:
1. `GG_CONFIG_PATH` environment variable (optional).
2. `receiver/certs/config.yaml`.
3. `~/greengrass/v2/config.yaml`.

It pulls the IoT data endpoint, thing name, and certificate bundle from that file before connecting over MQTT/TLS on port 8883.

### Running

```bash
cd receiver
python receiver/receiver.py
```

Logs emit connection status, subscribed topic details, and any messages received.

### `update` Action Workflow

When the receiver gets a message of the form:

```json
{
  "action": "update",
  "url": "https://example.com/archive.tar.gz",
  "filename": "archive.tar.gz",
  "command": "tar -xf archive.tar.gz"
}
```

It will:
1. Download the content from `url` (s3 pre-signed url in my case) into a temporary directory using `filename`.
2. Execute `command` inside that directory with `UPDATE_ARTIFACT_PATH` set to the downloaded file.
3. Remove the temporary directory when finished.

Failures (download or command execution) are logged with full stack traces.

---

## Sender Client

Path: `sender/sender.py`

- Uses constants defined at the top of the file for region, device list, log level, optional endpoint override, and broadcast enablement.
- Discovers the IoT endpoint automatically if none is specified.
- Publishes a default `start_detection` payload to each device topic: `devices/<thing_name>/commands`.
- Sleeps briefly between messages to avoid throttling.
- Optionally publishes the same payload to `devices/all/commands` when `ENABLE_BROADCAST` is set to `True`.

Update the constants as needed, then run:

```bash
cd sender
python sender.py
```

To send a custom payload, modify `build_sample_payload()` or wire in your own call.

---

## Testing the Update Flow

1. Start the receiver:
   ```bash
   python receiver/receiver.py
   ```
2. Modify `sender.py` to send an `update` payload, or publish manually:
   ```python
   payload = {
       "action": "update",
       "url": "https://example.com/script.sh",
       "filename": "script.sh",
       "command": "bash script.sh"
   }
   ```
3. Run the sender and monitor the receiver logs for download/execution messages.

Ensure downloaded artifacts and commands are from trusted sources before running them on a real device.

---

## Troubleshooting

- **TLS handshake failures**: confirm file paths in `config.yaml` point to valid certificates/keys with appropriate permissions.
- **Connection refused**: verify port 8883 is open and your device is allowed to connect to the IoT endpoint.
- **Publish succeeds but receiver is silent**: double-check the `thing_name` in the config matches the device ID used by the sender topic.
- **Update command errors**: review the receiver logs; the command exit code and stack trace are logged when failures occur.

---

## Appendix: mosquitto CLI Snippets

For ad-hoc testing you can still rely on `mosquitto` utilities (fill in real paths and endpoints):

```bash
mosquitto_sub -h <iot-endpoint> -p 8883 \
  --cafile <path/to/AmazonRootCA1.pem> \
  --cert <path/to/device.pem.crt> \
  --key <path/to/private.pem.key> \
  -t "devices/<device-id>/commands"
```

```bash
mosquitto_pub -h <iot-endpoint> -p 8883 \
  --cafile <path/to/AmazonRootCA1.pem> \
  --cert <path/to/device.pem.crt> \
  --key <path/to/private.pem.key> \
  -t "devices/<device-id>/commands" \
  -m '{"action": "ping"}'
```

These commands are optional but helpful during manual validation.
