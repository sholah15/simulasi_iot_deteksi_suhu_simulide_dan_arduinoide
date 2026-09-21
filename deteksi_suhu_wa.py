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

# MQTT CONFIGURATION
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "server/room/sensor")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

if not MQTT_USERNAME or not MQTT_PASSWORD:
    raise RuntimeError("MQTT_USERNAME dan MQTT_PASSWORD wajib diatur.")

# SERIAL CONFIGURATION
SERIAL_PORT = os.getenv("SERIAL_PORT", "/tmp/ttyV1")
BAUD_RATE = int(os.getenv("BAUD_RATE", "9600"))

# SENSOR THRESHOLD
TEMP_MIN = float(os.getenv("TEMP_MIN", "18.0"))
TEMP_MAX = float(os.getenv("TEMP_MAX", "30.0"))
HUM_MIN = float(os.getenv("HUM_MIN", "30.0"))
HUM_MAX = float(os.getenv("HUM_MAX", "70.0"))

# OPENWA CONFIGURATION
OPENWA_BASE_URL = os.getenv("OPENWA_BASE_URL", "http://localhost:2785")
SESSION_ID = os.getenv("OPENWA_SESSION_ID", "default")
API_KEY = os.getenv("OPENWA_API_KEY")
WHATSAPP_TARGET = os.getenv("WHATSAPP_TARGET")

# ALERT COOLDOWN (Diubah ke 300 detik / 5 menit agar tidak spam)
last_alert_time = 0
COOLDOWN_PERIOD = 300

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

def send_whatsapp_alert(message):
    global last_alert_time
    current_time = time.time()

    if current_time - last_alert_time < COOLDOWN_PERIOD:
        print("WhatsApp alert masih dalam cooldown.")
        return

    if not API_KEY or not WHATSAPP_TARGET:
        print("Peringatan: OPENWA_API_KEY atau WHATSAPP_TARGET belum diatur.")
        return

    url = f"{OPENWA_BASE_URL}/api/sessions/{SESSION_ID}/messages/send-text"
    payload = {"chatId": WHATSAPP_TARGET, "text": message}
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            print("Notifikasi WhatsApp berhasil dikirim!")
            last_alert_time = current_time
        else:
            print(f"Gagal mengirim WhatsApp (Status {response.status_code}): {response.text}")
    except Exception as e:
        print("Error koneksi ke OpenWA:", e)

def check_threshold(temp, hum):
    alert_messages = []

    if temp is None or hum is None:
        return

    if temp > TEMP_MAX:
        alert_messages.append(
            f"🔥 *PERINGATAN SUHU TINGGI!*\nSuhu server saat ini: *{temp}°C*\nMelewati batas maksimal {TEMP_MAX}°C"
        )
    elif temp < TEMP_MIN:
        alert_messages.append(
            f"❄️ *PERINGATAN SUHU TERLALU DINGIN!*\nSuhu server saat ini: *{temp}°C*\nDi bawah batas minimal {TEMP_MIN}°C"
        )

    if hum > HUM_MAX:
        alert_messages.append(
            f"💧 *PERINGATAN KELEMBAPAN TINGGI!*\nKelembapan server saat ini: *{hum}%*\nMelewati batas maksimal {HUM_MAX}%"
        )
    elif hum < HUM_MIN:
        alert_messages.append(
            f"⚠️ *PERINGATAN KELEMBAPAN RENDAH!*\nKelembapan server saat ini: *{hum}%*\nDi bawah batas minimal {HUM_MIN}%"
        )

    if alert_messages:
        full_message = "\n\n".join(alert_messages) + "\n\nMohon segera dicek ke ruang server!"
        threading.Thread(target=send_whatsapp_alert, args=(full_message,), daemon=True).start()

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        temp = payload.get("temperature")
        hum = payload.get("humidity")

        if temp is None or hum is None:
            print("MQTT payload tidak memiliki temperature/humidity")
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sensor_logs (temperature, humidity) VALUES (?, ?)",
            (temp, hum)
        )
        conn.commit()
        conn.close()

        print(f"Data masuk -> Temp: {temp}°C, Hum: {hum}%")
        check_threshold(float(temp), float(hum))

    except Exception as e:
        print("Error parsing MQTT message:", e)

def run_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.subscribe(MQTT_TOPIC)
            print(f"MQTT connected: {MQTT_BROKER}:{MQTT_PORT} | Subscribed: {MQTT_TOPIC}")
            client.loop_forever()
        except Exception as e:
            print("MQTT error, retrying in 5 seconds:", e)
            time.sleep(5)

def run_serial_bridge():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()

            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(f"Serial connected: {SERIAL_PORT}")

            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{"):
                        result = client.publish(MQTT_TOPIC, line)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            print("MQTT publish:", line)
                time.sleep(0.1)

        except Exception as e:
            print("Serial Bridge error, retrying in 5 seconds:", e)
            time.sleep(5)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT temperature, humidity, timestamp
        FROM sensor_logs
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    conn.close()

    data = [{"temperature": row[0], "humidity": row[1], "timestamp": row[2]} for row in reversed(rows)]
    return jsonify(data)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_mqtt, daemon=True).start()
    threading.Thread(target=run_serial_bridge, daemon=True).start()
    app.run(debug=True, use_reloader=False, port=5000)
