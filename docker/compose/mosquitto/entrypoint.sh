#!/bin/sh
# Mosquitto entrypoint — generate password file from env on every boot.
# This ensures env-defined creds always win over any persisted file, and
# avoids baking secrets into the image.
#
# Required env:
#   VULIS_MQTT_USER   — broker username
#   VULIS_MQTT_PASS   — broker password (plaintext; hashed on the fly)

set -eu

PASSWD_FILE="/mosquitto/config/passwd"
CONF_FILE="/mosquitto/config/mosquitto-platform.conf"

if [ -z "${VULIS_MQTT_USER:-}" ] || [ -z "${VULIS_MQTT_PASS:-}" ]; then
  echo "[entrypoint] VULIS_MQTT_USER and VULIS_MQTT_PASS must be set" >&2
  exit 1
fi

# Generate (or overwrite) the password file in batch mode.
# mosquitto_passwd -c errors out if the file already exists, so we remove
# it first. The volume mount means it persists across restarts.
rm -f "$PASSWD_FILE"
mosquitto_passwd -b -c "$PASSWD_FILE" "$VULIS_MQTT_USER" "$VULIS_MQTT_PASS"
chown mosquitto:mosquitto "$PASSWD_FILE" 2>/dev/null || true
chmod 600 "$PASSWD_FILE"

echo "[entrypoint] Mosquitto password file generated for user '$VULIS_MQTT_USER'"

# Hand off to the broker.
exec /usr/sbin/mosquitto -c "$CONF_FILE"
