import json
import sqlite3
import threading
import time
import requests
import os

from flask import Flask, jsonify, render_template
import paho.mqtt.client as mqtt
import serial


app = Flask(__name__)

DB_NAME = "server_room.db"


# ============================================================
# MQTT CONFIGURATION
# ============================================================

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC",
    "server/room/sensor"
)

MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")


if not MQTT_USERNAME or not MQTT_PASSWORD:
    raise RuntimeError(
        "MQTT_USERNAME dan MQTT_PASSWORD wajib diatur."
    )


# ============================================================
# SERIAL CONFIGURATION
# ============================================================

SERIAL_PORT = os.getenv(
    "SERIAL_PORT",
    "/tmp/ttyV1"
)

BAUD_RATE = int(
    os.getenv("BAUD_RATE", "9600")
)


# ============================================================
# SENSOR THRESHOLD
# ============================================================

TEMP_MIN = float(
    os.getenv("TEMP_MIN", "18.0")
)

TEMP_MAX = float(
    os.getenv("TEMP_MAX", "30.0")
)

HUM_MIN = float(
    os.getenv("HUM_MIN", "30.0")
)

HUM_MAX = float(
    os.getenv("HUM_MAX", "70.0")
)


# ============================================================
# OPENWA CONFIGURATION
# ============================================================

OPENWA_BASE_URL = os.getenv(
    "OPENWA_BASE_URL",
    "http://localhost:2785"
)

SESSION_ID = os.getenv(
    "OPENWA_SESSION_ID",
    "default"
)

API_KEY = os.getenv(
    "OPENWA_API_KEY"
)

WHATSAPP_TARGET = os.getenv(
    "WHATSAPP_TARGET"
)


# ============================================================
# ALERT COOLDOWN
# ============================================================

last_alert_time = 0
COOLDOWN_PERIOD = 5


# ============================================================
# DATABASE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_NAME)

    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# WHATSAPP ALERT
# ============================================================

def send_whatsapp_alert(message):

    global last_alert_time

    current_time = time.time()

    if current_time - last_alert_time < COOLDOWN_PERIOD:
        print("WhatsApp alert masih dalam cooldown.")
        return

    if not API_KEY:
        print(
            "Peringatan: OPENWA_API_KEY belum diatur."
        )
        return

    if not WHATSAPP_TARGET:
        print(
            "Peringatan: WHATSAPP_TARGET belum diatur."
        )
        return

    url = (
        f"{OPENWA_BASE_URL}"
        f"/api/sessions/{SESSION_ID}"
        f"/messages/send-text"
    )

    payload = {
        "chatId": WHATSAPP_TARGET,
        "text": message
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    try:

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=60
        )

        if response.status_code in (200, 201):

            print(
                "Notifikasi WhatsApp berhasil dikirim!"
            )

            last_alert_time = current_time

        else:

            print(
                f"Gagal mengirim WhatsApp "
                f"(Status {response.status_code}): "
                f"{response.text}"
            )

    except Exception as e:

        print(
            "Error koneksi ke OpenWA:",
            e
        )


# ============================================================
# CHECK SENSOR THRESHOLD
# ============================================================

def check_threshold(temp, hum):

    alert_messages = []

    if temp is None or hum is None:
        return

    if temp > TEMP_MAX:

        alert_messages.append(
            f"🔥 *PERINGATAN SUHU TINGGI!*\n"
            f"Suhu server saat ini: *{temp}°C*\n"
            f"Melewati batas maksimal {TEMP_MAX}°C"
        )

    elif temp < TEMP_MIN:

        alert_messages.append(
            f"❄️ *PERINGATAN SUHU TERLALU DINGIN!*\n"
            f"Suhu server saat ini: *{temp}°C*\n"
            f"Di bawah batas minimal {TEMP_MIN}°C"
        )


    if hum > HUM_MAX:

        alert_messages.append(
            f"💧 *PERINGATAN KELEMBAPAN TINGGI!*\n"
            f"Kelembapan server saat ini: *{hum}%*\n"
            f"Melewati batas maksimal {HUM_MAX}%"
        )

    elif hum < HUM_MIN:

        alert_messages.append(
            f"⚠️ *PERINGATAN KELEMBAPAN RENDAH!*\n"
            f"Kelembapan server saat ini: *{hum}%*\n"
            f"Di bawah batas minimal {HUM_MIN}%"
        )


    if alert_messages:

        full_message = (
            "\n\n".join(alert_messages)
            + "\n\nMohon segera dicek ke ruang server!"
        )

        threading.Thread(
            target=send_whatsapp_alert,
            args=(full_message,),
            daemon=True
        ).start()


# ============================================================
# MQTT MESSAGE
# ============================================================

def on_message(client, userdata, msg):

    try:

        payload = json.loads(
            msg.payload.decode()
        )

        temp = payload.get("temperature")
        hum = payload.get("humidity")

        if temp is None or hum is None:

            print(
                "MQTT payload tidak memiliki "
                "temperature/humidity"
            )

            return

        conn = sqlite3.connect(DB_NAME)

        c = conn.cursor()

        c.execute(
            """
            INSERT INTO sensor_logs
            (temperature, humidity)
            VALUES (?, ?)
            """,
            (temp, hum)
        )

        conn.commit()
        conn.close()

        print(
            f"Data masuk -> "
            f"Temp: {temp}°C, "
            f"Hum: {hum}%"
        )

        check_threshold(
            float(temp),
            float(hum)
        )

    except Exception as e:

        print(
            "Error parsing MQTT message:",
            e
        )


# ============================================================
# MQTT SUBSCRIBER
# ============================================================

def run_mqtt():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    client.on_message = on_message

    try:

        client.connect(
            MQTT_BROKER,
            MQTT_PORT,
            60
        )

        client.subscribe(
            MQTT_TOPIC
        )

        print(
            f"MQTT connected: "
            f"{MQTT_BROKER}:{MQTT_PORT}"
        )

        print(
            f"MQTT subscribed: "
            f"{MQTT_TOPIC}"
        )

        client.loop_forever()

    except Exception as e:

        print(
            "MQTT error:",
            e
        )


# ============================================================
# SERIAL -> MQTT BRIDGE
# ============================================================

def run_serial_bridge():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD
    )

    try:

        client.connect(
            MQTT_BROKER,
            MQTT_PORT,
            60
        )

        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE
        )

        print(
            f"Serial connected: "
            f"{SERIAL_PORT}"
        )

        while True:

            if ser.in_waiting > 0:

                line = (
                    ser.readline()
                    .decode("utf-8")
                    .strip()
                )

                if line.startswith("{"):

                    result = client.publish(
                        MQTT_TOPIC,
                        line
                    )

                    if result.rc == mqtt.MQTT_ERR_SUCCESS:

                        print(
                            "MQTT publish:",
                            line
                        )

            time.sleep(0.1)

    except Exception as e:

        print(
            "Serial Bridge error:",
            e
        )


# ============================================================
# FLASK
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


@app.route("/api/data")
def get_data():

    conn = sqlite3.connect(DB_NAME)

    c = conn.cursor()

    c.execute("""
        SELECT temperature,
               humidity,
               timestamp
        FROM sensor_logs
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = c.fetchall()

    conn.close()

    data = []

    for row in reversed(rows):

        data.append({
            "temperature": row[0],
            "humidity": row[1],
            "timestamp": row[2]
        })

    return jsonify(data)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    init_db()

    threading.Thread(
        target=run_mqtt,
        daemon=True
    ).start()

    threading.Thread(
        target=run_serial_bridge,
        daemon=True
    ).start()

    app.run(
        debug=True,
        use_reloader=False,
        port=5000
    )
