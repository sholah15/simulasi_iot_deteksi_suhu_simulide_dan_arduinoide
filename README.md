# Simulasi IoT Deteksi Suhu (SimulIDE & Arduino IDE)

Proyek ini merupakan simulasi sistem pemantauan suhu berbasis IoT (*Internet of Things*). Sistem membaca data suhu menggunakan sensor DHT di **SimulIDE**, mengirimkan data melalui port serial virtual, memprosesnya via **MQTT Broker**, menyajikannya pada **Web Dashboard (Flask)**, serta mengirimkan notifikasi peringatan otomatis ke **WhatsApp (OpenWA)** jika suhu berada di luar batas aman.

---

## 🛠️ Fitur Utama

- **Simulasi Hardware**: Menggunakan SimulIDE untuk mensimulasikan papan Arduino Uno dan sensor DHT.
- **Virtual Serial Bridge**: Mengatur komunikasi serial antar komponen menggunakan `socat`.
- **MQTT Broker**: Mengirimkan telemetry data secara real-time menggunakan Mosquitto.
- **Web Dashboard**: Antarmuka berbasis Flask untuk memantau data suhu.
- **Notifikasi WhatsApp**: Integrasi dengan OpenWA Docker untuk mengirim pesan otomatis saat suhu terlalu dingin (<17°C) atau terlalu panas (>30°C).

---

## 📋 Prasyarat (*Prerequisites*)

Pastikan perangkat Anda (Linux OS) telah memiliki dependensi berikut:

- **Linux OS** (Panduan ini disesuaikan untuk distro berbasis Arch/Manjaro/Ubuntu)
- **SimulIDE**
- **Arduino IDE** (dengan *Library* `DHT sensor library by Adafruit`)
- **Python 3** & `pip`
- **Docker** & **Docker Compose**
- **socat** & **Mosquitto Broker**

---

## 🚀 Panduan Langkah demi Langkah

### 1. Persiapan Simulasi Hardware (SimulIDE & Arduino IDE)

1. Buka **SimulIDE**, klik ikon **Open**, lalu muat file simulasi:
   `deteksi_suhu.sim1`
2. Buka **Arduino IDE**, masuk ke **Library Manager**, lalu instal pustaka:
   - `DHT sensor library by Adafruit`
3. Tutup Arduino IDE.
4. Pada **SimulIDE**, buka **Setting** > **Compiler Setting**.
5. Masukkan *path* instalasi Arduino IDE pada bagian **Tool Path**.
   *(Jika berhasil, log `"Found Arduino Version 2"` akan muncul di terminal SimulIDE)*.
6. Pada editor SimulIDE, buka file source code Arduino:
   `deteksi_suhu.ino`
7. Klik **Compile**, lalu klik **Upload** untuk memasukkan program ke modul Arduino Uno.
8. Jalankan simulasi pada SimulIDE (klik tombol Power).
9. Untuk melihat data serial:
   - Klik kanan pada komponen **Arduino Uno**.
   - Pilih menu `mega328-109` > `Open Serial Monitor` > `USART1`.

---

### 2. Konfigurasi Virtual Port, Service, & Web Dashboard

1. **Jalankan Virtual Serial Port (`socat`)**
   Buka terminal Linux dan jalankan perintah berikut (biarkan terminal tetap terbuka):
   ```bash
   socat -d -d PTY,link=/tmp/ttyV0,raw,echo=0 PTY,link=/tmp/ttyV1,raw,echo=0
   ```

2. **Setup Environment Python**
   Buka terminal baru, buat dan aktifkan virtual environment:
   ```bash
   python3 -m venv ve
   source ve/bin/activate
   pip install flask paho-mqtt pyserial
   ```

3. **Instal & Jalankan Mosquitto MQTT Broker**
   ```bash
   # Untuk Arch/Manjaro:
   sudo pacman -S mosquitto

   # Jalankan service Mosquitto
   sudo systemctl enable --now mosquitto
   ```

4. **Buat Kredensial Mosquitto**
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/passwd nama_user
   ```
   *Atur `MQTT_USERNAME` dan `MQTT_PASSWORD` di file `run.sh` sesuai dengan kredensial di atas.*

5. **Jalankan Application Server**
   ```bash
   chmod +x run.sh
   ./run.sh
   ```
   Akses Web Dashboard pada peramban web di: `http://localhost:5000`

---

### 3. Integrasi Notifikasi WhatsApp (OpenWA)

1. **Instal Pustaka Python `requests`** *(pada virtual environment)*:
   ```bash
   pip install requests
   ```

2. **Menjalankan Container OpenWA**:
   ```bash
   git clone https://github.com/rmyndharis/OpenWA.git
   cd OpenWA
   docker compose -f docker-compose.dev.yml up -d
   ```

3. **Ambil API Key OpenWA**:
   ```bash
   docker exec openwa-api cat /app/data/.api-key
   ```

4. **Konfigurasi Session WhatsApp**:
   - Buka browser dan kunjungi `http://localhost:2785`.
   - Masukkan **API Key** yang telah ditautkan.
   - Masuk ke menu **Sessions** > **New Session** > Beri nama session > **Create** > **Start**.
   - Pindai (**Scan**) QR Code yang muncul menggunakan aplikasi WhatsApp di smartphone Anda.
   - Klik tombol **View** pada kotak Session, lalu salin **Session ID**.

5. **Menjalankan Service WhatsApp**:
   - Sesuaikan nilai `OPENWA_SESSION_ID`, `OPENWA_API_KEY`, dan `WHATSAPP_TARGET` pada file `run.sh`.
   - Jalankan script notifikasi:
     ```bash
     ./run.sh deteksi_suhu_wa.py
     ```

---

## 🧪 Pengujian Notifikasi Suhu

1. Ubah parameter suhu pada sensor DHT di **SimulIDE** menjadi kurang dari **17°C** atau lebih dari **30°C**.
2. Sistem akan mendeteksi kondisi abnormal dan mengirimkan pesan notifikasi peringatan ke nomor WhatsApp target.
3. *Tips Pengujian:* Anda dapat menyesuaikan nilai `COOLDOWN_PERIOD = 300` menjadi `COOLDOWN_PERIOD = 10` di file `deteksi_suhu_wa.py` untuk mempercepat interval pengiriman pesan saat melakukan *testing*.

---

## 📁 Struktur Repositori

```text
├── deteksi_suhu/
│   ├── deteksi_suhu.hex      # Firmware Arduino
│   ├── deteksi_suhu.sim1     # File skema rangkaian SimulIDE
│   └── deteksi_suhu.ino      # Source code program Arduino
├── deteksi_suhu.py           # Script pemantau suhu Web Dashboard
├── deteksi_suhu_wa.py        # Script pemantau suhu & pengirim notifikasi WhatsApp
├── run.sh                    # Script penjalankan aplikasi
└── README.md                 # Dokumen panduan penggunaan
```
