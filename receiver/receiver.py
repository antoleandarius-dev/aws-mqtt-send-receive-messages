"""Refined MQTT receiver client with improved configurability and resiliency."""

import json
import logging
import os
import shlex
import signal
import ssl
import subprocess
import tempfile
import threading
import urllib.request
import shutil

import paho.mqtt.client as mqtt
import yaml


DEFAULT_PORT = 8883
DEFAULT_TOPIC_TEMPLATE = "devices/{thing_name}/commands"
ENV_CONFIG_PATH = "GG_CONFIG_PATH"


def resolve_config_path(override_path=None):
    """Locate the Greengrass config file, honoring overrides and known defaults."""
    candidates = []
    if override_path:
        candidates.append(override_path)

    env_path = os.getenv(ENV_CONFIG_PATH)
    if env_path:
        candidates.append(env_path)

    local_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "certs", "config.yaml")
    candidates.append(local_path)

    default_path = os.path.join(os.path.expanduser("~"), "greengrass", "v2", "config.yaml")
    candidates.append(default_path)

    for path in candidates:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded):
            return expanded

    raise FileNotFoundError(
        "Could not locate Greengrass config file. "
        f"Tried: {', '.join(os.path.expanduser(p) for p in candidates)}"
    )


def load_config(config_path):
    """Read Greengrass config YAML and extract MQTT-related settings."""
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Config file not found at {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML config at {config_path}") from exc

    system_config = config.get("system") or {}
    nucleus_config = (
        config.get("services", {})
        .get("aws.greengrass.Nucleus", {})
        .get("configuration", {})
    )

    endpoint = nucleus_config.get("iotDataEndpoint") or os.getenv("AWS_IOT_ENDPOINT")
    thing_name = system_config.get("thingName") or os.getenv("GG_THING_NAME")
    certificate_path = system_config.get("certificateFilePath")
    private_key_path = system_config.get("privateKeyPath")
    root_ca_path = system_config.get("rootCaPath")

    missing = [
        name
        for name, value in {
            "iotDataEndpoint": endpoint,
            "thingName": thing_name,
            "certificateFilePath": certificate_path,
            "privateKeyPath": private_key_path,
            "rootCaPath": root_ca_path,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required config values: {', '.join(missing)}")

    return {
        "endpoint": endpoint,
        "thing_name": thing_name,
        "certificate_path": certificate_path,
        "private_key_path": private_key_path,
        "root_ca_path": root_ca_path,
        "port": DEFAULT_PORT,
    }


def configure_logging(level):
    """Initialize logging for the receiver using the requested verbosity."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger("receiver-client")


def build_client(config, topic, logger):
    """Create the MQTT client with TLS, reconnect settings, and message handlers."""
    thing_name = config["thing_name"]
    endpoint = config["endpoint"]
    client = mqtt.Client(client_id=thing_name)
    client.tls_set(
        ca_certs=config["root_ca_path"],
        certfile=config["certificate_path"],
        keyfile=config["private_key_path"],
        tls_version=ssl.PROTOCOL_TLSv1_2,
    )
    client.tls_insecure_set(False)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    def on_connect(inner_client, userdata, flags, reason_code):
        if reason_code == 0:
            logger.info("Connected to endpoint %s", endpoint)
            inner_client.subscribe(topic)
            logger.info("Subscribed to topic %s", topic)
        else:
            logger.error(
                "Failed to connect (code=%s): %s",
                reason_code,
                mqtt.error_string(reason_code),
            )

    def on_message(inner_client, userdata, message):
        payload_text = message.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(payload_text)
            logger.info("Message on %s: %s", message.topic, payload)
            # handle file downloads using URL, filename and command to execute
            if payload.get("action") == "update":
                url = payload.get("url")
                command = payload.get("command")
                filename = payload.get("filename")
                if not url or not command or not filename:
                    logger.error("Update message missing url, command, or filename")
                    return
                temp_dir = None
                try:
                    safe_name = os.path.basename(filename)
                    if not safe_name:
                        raise ValueError("Invalid filename provided")
                    temp_dir = tempfile.mkdtemp(prefix="receiver-update-")
                    download_path = os.path.join(temp_dir, safe_name)
                    with urllib.request.urlopen(url) as response, open(download_path, "wb") as temp_file:
                        temp_file.write(response.read())
                    logger.info("Downloaded update artifact to %s", download_path)
                except Exception:
                    logger.exception("Failed to download update artifact from %s", url)
                    if temp_dir:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    return
                try:
                    cmd = shlex.split(command)
                    env = os.environ.copy()
                    env["UPDATE_ARTIFACT_PATH"] = download_path
                    subprocess.run(cmd, check=True, env=env, cwd=temp_dir)
                    logger.info("Executed update command: %s", command)
                except Exception:
                    logger.exception("Update command failed: %s", command)
                finally:
                    try:
                        if temp_dir:
                            shutil.rmtree(temp_dir)
                            logger.debug("Removed temporary artifact directory %s", temp_dir)
                    except OSError:
                        logger.warning("Could not remove temporary artifact directory %s", temp_dir)

        except json.JSONDecodeError:
            logger.warning(
                "Received non-JSON payload on %s: %s", message.topic, payload_text
            )

    def on_disconnect(inner_client, userdata, reason_code):
        if reason_code == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Disconnected cleanly")

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    return client


def run_client(client, config, logger):
    """Maintain the MQTT connection until a termination signal is received."""
    stop_event = threading.Event()

    def handle_signal(signum, _frame):
        logger.info("Signal %s received, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        client.connect(config["endpoint"], config["port"])
    except Exception as exc:  # noqa: BLE001 - surface connection issues
        logger.exception("Failed to establish MQTT connection: %s", exc)
        raise

    client.loop_start()
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1)
    finally:
        logger.info("Stopping MQTT client loop")
        client.loop_stop()
        client.disconnect()


def main():
    """Bootstrap logging, load configuration, and start the MQTT receiver."""
    logger = configure_logging("INFO")

    config_path = resolve_config_path()
    logger.info("Using config at %s", config_path)

    config = load_config(config_path)
    topic = DEFAULT_TOPIC_TEMPLATE.format(thing_name=config["thing_name"])

    client = build_client(config, topic, logger)
    run_client(client, config, logger)


if __name__ == "__main__":
    main()
