"""
Smart Home HMI Dashboard - Dual Protocol Server
(Integrated with Dynamic Enterprise Zones, Bidirectional Control & POC Pager Adaptive Runtime)
"""

import asyncio
import json
import os
import random
import threading
import time
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import (
    ControllerBoard,
    FunctionBlock,
    IOMapping,
    Project,
    WidgetNode,
    db,
    AutomationRule
)
from werkzeug.utils import secure_filename
import websockets

WS_LOOP = None

# ──────────────────────────────────────────────
# Inisialisasi Aplikasi Flask & Database SQLite
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'Smart_Home_FieldFlow'
app.config['SECRET_KEY'] = 'smart-home-pbl-secret-key'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Jika tidak ada sesi 'logged_in', lempar paksa ke halaman login
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(
    basedir, 'smarthome_studio.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

with app.app_context():
  db.create_all()
  print("[DATABASE] Skema tabel Studio IoT berhasil diinisialisasi!")

connected_devices = {}
last_known_status = {}

# Flag & State untuk Virtual Panel
REAL_PANEL_CONNECTED = False
virtual_state = {
    "power": {
        "voltage": 220.5,
        "current": 2.31,
        "power": 485.0,
        "energy": 8.52,
        "frequency": 50.0,
        "pf": 0.98,
    },
    "relay": [False, False, False, False, False, False, False, False],
    "alarm": {
        "fire": False,
        "gas": False,
        "pir": False,
        "smoke": False,
        "door": False,
        "flood": False,
    },
    "environment": {
        "temperature": 28.5,
        "gas_ppm": 312.0
    }
}
last_known_alarms = {
    "fire": False,
    "gas": False,
    "pir": False,
    "smoke": False,
    "door": False,
    "flood": False,
}

# ==========================================
# MIDDLEWARE CORE: RUNTIME & BINDING REGISTRY
# ==========================================

# Menyimpan state terkini dari seluruh variabel sistem
RUNTIME_REGISTRY = {
    "env_suhu_kamar": 0.0,
    "env_humidity_kamar": 0,
    "exhaust": False,
    "lampu_utama": False,
    "gate_2": False,     # Tambahan untuk POC
    "lampu_10": False    # Tambahan untuk POC
}

# INBOUND: Mapping dari (slave_id, sensor_type, parameter) -> Nama Variabel Runtime
INBOUND_BINDING = {
    (1, "DHT11", "temperature"): "env_suhu_kamar",
    (1, "DHT11", "humidity"): "env_humidity_kamar"
}

# OUTBOUND: Mapping dari Nama Variabel Runtime -> Alamat Hardware Fisik
OUTBOUND_BINDING = {
    "exhaust": {"slave_id": 2, "type": "relay", "channel": 2},
    "lampu_utama": {"slave_id": 2, "type": "relay", "channel": 0},
    "gate_2": {"slave_id": 2, "type": "relay", "channel": 1},  # Sesuaikan channel
    "lampu_10": {"slave_id": 2, "type": "relay", "channel": 3} # Sesuaikan channel
}

@app.route('/api/automation/<int:project_id>', methods=['POST'])
@login_required
def add_automation_rule(project_id):
    data = request.json
    try:
        new_rule = AutomationRule(
            project_id=project_id,
            rule_name=data['rule_name'],
            condition_widget=data['condition_widget'],
            condition_operator=data['condition_operator'],
            condition_value=data['condition_value'],
            action_widget=data['action_widget'],
            action_state=data['action_state']
        )
        db.session.add(new_rule)
        db.session.commit()
        return jsonify({"status": "success", "message": "Aturan automasi ditambahkan."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/automation/delete/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_automation_rule(rule_id):
    try:
        rule = AutomationRule.query.get_or_404(rule_id)
        db.session.delete(rule)
        db.session.commit()
        return jsonify({"status": "success", "message": "Aturan berhasil dihapus."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Jika pengguna sudah login, langsung arahkan ke Dashboard
    if 'logged_in' in session:
        return redirect(url_for('dashboard')) # Pastikan fungsi route '/' Anda bernama 'dashboard' atau sesuaikan namanya

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Kredensial sementara (Admin)
        if username == 'admin' and password == 'admin':
            session['logged_in'] = True
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Username atau password salah!")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() # Hapus semua sesi
    return redirect(url_for('login'))

# ──────────────────────────────────────────────
# Pengepakan Data untuk Web UI & Lokasi
# ──────────────────────────────────────────────
def get_web_payload(status_payload):
  try:
    relays = status_payload.get('relay', [])
    return {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'telemetry': status_payload.get('power', {}),
        'environment': status_payload.get('environment', {}),
        'relays': {
            f'relay_{i}': relays[i] if len(relays) > i else False
            for i in range(8)
        },
        'alarms': status_payload.get(
            'alarm', {}
        ),
        'sensors': {
            'dapur': {
                'gas': 'ACTIVE'
                if status_payload.get('alarm', {}).get('gas')
                else 'AMAN'
            },
            'ruang_tamu': {
                'pir': 'ACTIVE'
                if status_payload.get('alarm', {}).get('pir')
                else 'AMAN'
            },
            'kamar': {
                'fire': 'ACTIVE'
                if status_payload.get('alarm', {}).get('fire')
                else 'AMAN'
            },
        },
    }
  except Exception as e:
    print(f"[WS-5000] Error mapping payload: {e}")
    return {}

def get_alarm_location(alarms):
  if alarms.get("fire"): return "Bedroom"
  if alarms.get("gas"): return "Kitchen"
  if alarms.get("pir"): return "Living Room"
  if alarms.get("door"): return "Gate"
  return "Unknown"

# ──────────────────────────────────────────────
# Task: Virtual Main Panel (Event-Driven Data Generator)
# ──────────────────────────────────────────────
async def virtual_panel_task():
  """Berperan sebagai panel01 mengirim data dummy hingga panel asli terkoneksi."""
  global virtual_state, last_known_status, REAL_PANEL_CONNECTED
  print("[VIRTUAL PANEL] Aktif. Mengirim data simulasi dan update sensor...")

  while True:
    await asyncio.sleep(3) # Update setiap 3 detik
    if REAL_PANEL_CONNECTED:
      print("[VIRTUAL PANEL] Berhenti selamanya (Hardware asli mengambil alih).")
      break

    # 1. Update data internal simulasi Web Dashboard
    virtual_state["power"]["voltage"] = round(random.uniform(218.0, 222.0), 1)
    virtual_state["power"]["current"] = round(random.uniform(1.0, 4.0), 2)
    virtual_state["power"]["power"] = round(virtual_state["power"]["voltage"] * virtual_state["power"]["current"], 1)
    virtual_state["environment"]["temperature"] = round(random.uniform(25.0, 31.5), 1)
    virtual_state["environment"]["gas_ppm"] = round(random.uniform(290.0, 350.0), 1)

    status_packet = {
        "type": "status",
        "from": "panel01",
        "to": "all",
        "timestamp": int(time.time()),
        "payload": virtual_state,
    }
    message = json.dumps(status_packet)
    last_known_status = virtual_state
    socketio.emit('update_status', get_web_payload(last_known_status))

    for d_id, ws in list(connected_devices.items()):
      try:
        await ws.send(message)
      except:
        pass

    power_update_msg = json.dumps({
        "type": "sensor_update",
        "from": "server",
        "to": "all",
        "payload": {
            "page_id": "power_main",
            "data": {
                "voltage": virtual_state["power"]["voltage"],
                "current": virtual_state["power"]["current"],
                "power": virtual_state["power"]["power"],
                "energy": virtual_state["power"]["energy"]
            }
        }
    })
    
    for d_id, ws in list(connected_devices.items()):
        if d_id.startswith("pager"):
            asyncio.run 
            try:
                await ws.send(power_update_msg)
            except:
                pass

    # 2. Ambil data widget SENSOR murni dari SQLite untuk dikirimkan secara Event-Driven
    with app.app_context():
        proj = Project.query.first()
        sensor_widgets = WidgetNode.query.filter(WidgetNode.widget_type.like('SENSOR_%')).all() if proj else []

    # 3. Generate dan Push update untuk masing-masing Instance Halaman (page_id)

    for w in sensor_widgets:
        page_id = f"env_{w.label_name}"
        data_payload = {}
        
        # --- PENDEKATAN DINAMIS (TANPA HARDCODE KAKU) ---
        # 1. Jika sensor sudah dikenali secara khusus di simulasi:
        if w.widget_type == 'SENSOR_TEMP':
            primary_val = virtual_state["environment"]["temperature"]
            data_payload = {"temperature": primary_val, "humidity": random.randint(55, 75)}
        elif w.widget_type == 'SENSOR_POWER':
            primary_val = virtual_state["power"]["power"]
            data_payload = {"voltage": virtual_state["power"]["voltage"], "power": primary_val}
            
        # 2. DYNAMIC FALLBACK: Untuk SEMUA sensor jenis baru di masa depan!
        else:
            # Cek apakah nama tipe sensornya berbau digital (PIR/FIRE/DOOR/SMOKE dll)
            if any(keyword in w.widget_type for keyword in ['PIR', 'FIRE', 'DOOR', 'SMOKE']):
                primary_val = random.choice([0, 1])
                data_payload = {"status": "ALARM" if primary_val else "AMAN"}
            else:
                # Jika bukan, anggap sensor analog (misal: SENSOR_CAHAYA, SENSOR_AIR)
                primary_val = round(random.uniform(10.0, 99.0), 1)
                data_payload = {"value": primary_val}

        # 3. Injeksi Dinamis ke Memori ST (Apapun nama labelnya, otomatis masuk!)
        RUNTIME_REGISTRY[w.label_name] = primary_val

        update_msg = json.dumps({
            "type": "sensor_update",
            "from": "server",
            "to": "all",
            "payload": {
                "page_id": page_id,
                "data": data_payload
            }
        })
        
        for d_id, ws in list(connected_devices.items()):
            if d_id.startswith("pager"):
                try: asyncio.run_coroutine_threadsafe(ws.send(update_msg), WS_LOOP)
                except: pass

# ──────────────────────────────────────────────
# Task: ST Engine - Automation Scan Cycle
# ──────────────────────────────────────────────
async def st_engine_task():
    global WS_LOOP, virtual_state
    print("[ST ENGINE] Aktif. Memantau aturan automasi setiap 1 detik...")
    
    while True:
        await asyncio.sleep(1) # Siklus pemindaian 1 detik
        
        with app.app_context():
            # Baca semua aturan yang berstatus aktif
            rules = AutomationRule.query.filter_by(is_active=True).all()
            
            for rule in rules:
                # 1. Baca nilai sensor saat ini dari Memory Environment
                current_val = RUNTIME_REGISTRY.get(rule.condition_widget)
                if current_val is None:
                    continue # Lewati jika sensor belum pernah mengirim data
                    
                # 2. Evaluasi Logika (IF)
                is_met = False
                if rule.condition_operator == '>': is_met = current_val > rule.condition_value
                elif rule.condition_operator == '<': is_met = current_val < rule.condition_value
                elif rule.condition_operator == '==': is_met = current_val == rule.condition_value
                    
                # 3. Eksekusi Aksi (THEN) dengan Anti-Spam
                if is_met and rule.last_triggered_state != True:
                    print(f"\n[ST ENGINE] ⚙️ Rule '{rule.rule_name}' TERPICU! ({current_val} {rule.condition_operator} {rule.condition_value})")
                    
                    rule.last_triggered_state = True
                    db.session.commit()
                    
                    # --- EKSEKUSI HARDWARE-LEVEL (GPIO) ---
                    try:
                        gpio_pin = int(rule.action_widget) # Membaca angka pin GPIO (misal: 23)
                        target_state = rule.action_state
                        
                        # Lakukan Reverse-Lookup untuk menyinkronkan animasi UI di Web
                        channel_idx = None
                        pager_var_name = f"gpio_{gpio_pin}"
                        
                        mapping = IOMapping.query.filter_by(gpio_pin=gpio_pin).first()
                        if mapping:
                            channel_idx = mapping.channel_index
                            w = WidgetNode.query.get(mapping.widget_id)
                            if w: pager_var_name = w.label_name
                            
                        # 1. Update Animasi Web Dashboard (Jika pin tersebut ada di kanvas HMI)
                        if channel_idx is not None and channel_idx < len(virtual_state["relay"]):
                            virtual_state["relay"][channel_idx] = target_state
                            socketio.emit("update_status", get_web_payload(virtual_state))
                            
                        # 2. Dispatch Perintah Fisik Langsung ke ESP32 Fajar berdasarkan GPIO
                        cmd_payload = json.dumps({
                            "type": "hardware_command",
                            "target": "main_panel_01",
                            "payload": {
                                "slave_id": 1,
                                "port": f"D{gpio_pin}", # Format standar digital (D23, D22, dst)
                                "pin": gpio_pin,        # Angka pin absolut
                                "state": target_state
                            }
                        })
                        
                        # 3. Siarkan Payload ke Hardware & Pager Mobile
                        for d_id, ws in list(connected_devices.items()):
                            if d_id.startswith("main_panel") or d_id.startswith("panel"):
                                try: asyncio.run_coroutine_threadsafe(ws.send(cmd_payload), WS_LOOP)
                                except: pass
                            elif d_id.startswith("pager"):
                                event_msg = json.dumps({"type": "status_update", "from": "server", "to": "all", "payload": {"variable": pager_var_name, "value": target_state}})
                                try: asyncio.run_coroutine_threadsafe(ws.send(event_msg), WS_LOOP)
                                except: pass
                                
                    except ValueError:
                        print(f"[ST ENGINE] ⚠️ Error: '{rule.action_widget}' bukan format GPIO yang valid.")

                # 4. Reset Kunci jika kondisi kembali normal
                elif not is_met and rule.last_triggered_state == True:
                    print(f"[ST ENGINE] ♻️ Rule '{rule.rule_name}' KEMBALI NORMAL.")
                    rule.last_triggered_state = False
                    db.session.commit()

# ──────────────────────────────────────────────
# Route Persistensi & Compiler Studio
# ──────────────────────────────────────────────
@app.route('/api/save_studio/<int:project_id>', methods=['POST'])
def save_studio_state(project_id):
  """Menyimpan layout dan mem-push secara dinamis ke Pager (Live Reload)."""
  try:
    data = request.json
    proj = Project.query.get_or_404(project_id)

    if 'background_image' in data:
      proj.background_image = data['background_image']

    board = ControllerBoard.query.filter_by(project_id=proj.id).first()
    if not board:
      board = ControllerBoard(project_id=proj.id, device_id="panel01")
      db.session.add(board)
    board.board_name = data.get('board_name', 'ESP32-WROOM-32')

    fb = FunctionBlock.query.filter_by(board_id=board.id).first()
    if not fb:
      fb = FunctionBlock(board_id=board.id, fb_identifier="FB_RELAY_1")
      db.session.add(fb)
    fb.module_type = data.get('relay_type', 'RELAY_8CH')
    fb.total_channels = int(data.get('total_channels', 8))

    WidgetNode.query.filter_by(project_id=proj.id).delete()
    IOMapping.query.filter_by(fb_id=fb.id).delete()

    for idx, w_item in enumerate(data.get('widgets', [])):
      new_w = WidgetNode(
          project_id=proj.id,
          widget_id=w_item['widget_id'],
          label_name=w_item['label_name'],
          zone_name=w_item.get('zone_name', 'Area Umum'),
          widget_type=w_item['widget_type'],
          pos_x=float(w_item['pos_x']),
          pos_y=float(w_item['pos_y']),
      )
      db.session.add(new_w)
      db.session.flush()

      if 'mapping' in w_item and w_item['mapping']:
        new_m = IOMapping(
            widget_id=new_w.id,
            fb_id=fb.id,
            channel_index=int(w_item['mapping']['channel_index']),
            gpio_pin=int(w_item['mapping']['gpio_pin']),
            active_low=bool(w_item['mapping'].get('active_low', False)),
            array_order=idx,
        )
        db.session.add(new_m)

    proj.updated_at = int(time.time())
    db.session.commit()

    # =====================================================================
    # LIVE RELOAD & SSOT MANIFEST DEPLOYMENT
    # =====================================================================
    try:
      global WS_LOOP
      if WS_LOOP and WS_LOOP.is_running():
        all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
        
        relay_items = []
        sensor_pages = []
        hw_instances = [] # Array untuk manifest ESP32 (Sensor)
        hw_actuators = [] # <--- INI VARIABEL YANG HILANG (Untuk Relay)

        for idx, w in enumerate(all_widgets):
          # A. Kumpulkan data untuk Sinkronisasi UI (Pager)
          if w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
              is_on = virtual_state["relay"][idx] if idx < len(virtual_state["relay"]) else False
              relay_items.append({"variable": w.label_name, "value": is_on})
          elif w.widget_type.startswith('SENSOR_'):
              sensor_pages.append({
                  "page_id": f"env_{w.label_name}",
                  "sensor_type": w.widget_type,
                  "title": w.zone_name.upper() if w.zone_name else "AREA UMUM"
              })

          # B. Kumpulkan data untuk Hardware Manifest (ESP32 Fajar)
          if w.mapping:
              if w.widget_type.startswith('SENSOR_'):
                  hw_sensor_type = "UNKNOWN"
                  if w.widget_type == 'SENSOR_TEMP': hw_sensor_type = "DHT11"
                  elif w.widget_type == 'SENSOR_GAS': hw_sensor_type = "MQ_ANALOG"
                  elif w.widget_type == 'SENSOR_PIR': hw_sensor_type = "PIR_DIGITAL"
                  elif w.widget_type == 'SENSOR_POWER': hw_sensor_type = "PZEM"

                  raw_pin = w.mapping.gpio_pin 
                  pin_str = f"A{raw_pin}" if hw_sensor_type == "MQ_ANALOG" else f"D{raw_pin}"
                  
                  hw_instances.append({
                      "instance_id": w.label_name,
                      "sensor_type": hw_sensor_type,
                      "port": pin_str, 
                      "sample_ms": 1000 if hw_sensor_type == "MQ_ANALOG" else 2000
                  })
              
              elif w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
                  raw_pin = w.mapping.gpio_pin
                  channel_idx = w.mapping.channel_index
                  is_active_low = w.mapping.active_low if hasattr(w.mapping, 'active_low') else False
                  trigger_level = 0 if is_active_low else 1
                  hw_actuators.append({
                      "instance_id": w.label_name,
                      "module_type": "RELAY",
                      "channel": channel_idx,
                      "port": f"D{raw_pin}",
                      "active_level": trigger_level,
                      "initial_state": False
                  })

        # 1. Pesan untuk UI Web Dashboard
        msg_relay = json.dumps({"type": "runtime_list", "from": "server", "to": "all", "payload": {"relay": relay_items}})
        msg_sensor = json.dumps({"type": "runtime_sensor_manifest", "from": "server", "to": "all", "payload": {"sensor_pages": sensor_pages}})
        
        # 2. SSoT Manifest Resmi untuk Slave 1 (Khusus Sensor)
        deploy_manifest = json.dumps({
            "type": "deploy_manifest",
            "target": "main_panel_01",
            "version": 1,
            "slave_id": 1,
            "instances": hw_instances
        })

        # 3. Manifest Command Khusus untuk Slave 2 (Khusus Relay/Aktuator)
        command_manifest = json.dumps({
            "type": "command",
            "target": "main_panel_01",
            "slave_id": 1,
            "actuators": hw_actuators
        })

        # Broadcast via WebSocket
        for d_id, ws in list(connected_devices.items()):
          if d_id.startswith("pager"):
            asyncio.run_coroutine_threadsafe(ws.send(msg_relay), WS_LOOP)
            asyncio.run_coroutine_threadsafe(ws.send(msg_sensor), WS_LOOP)
          elif d_id.startswith("main_panel") or d_id.startswith("panel"):
            # Tembakkan KEDUA manifest ke Main Panel sebagai Gateway
            asyncio.run_coroutine_threadsafe(ws.send(deploy_manifest), WS_LOOP)
            asyncio.run_coroutine_threadsafe(ws.send(command_manifest), WS_LOOP)
            
        print("[SERVER] ⚡ Layout disimpan! Dual Manifest (Sensor & Relay) dikirim ke Main Panel.")
        print(f"  ↳ Sensor Manifest: {deploy_manifest}")
        print(f"  ↳ Relay Command  : {command_manifest}")
    except Exception as e:
      print(f"[SERVER] ⚠️ Gagal push live reload/manifest: {e}")
    # =====================================================================

    return jsonify({"status": "success", "message": "Perubahan Studio berhasil disimpan ke SQLite!"}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": f"Gagal menyimpan ke database: {str(e)}"}), 500

@app.route('/api/generate_json/<int:project_id>', methods=['GET'])
def generate_project_json(project_id):
  """ENGINE COMPILER: Menerjemahkan wiring visual & zona menjadi format Topologi Ringkas"""
  try:
    proj = Project.query.get_or_404(project_id)
    board = ControllerBoard.query.filter_by(project_id=proj.id).first()
    if not board: 
        return jsonify({"status": "error", "message": "Controller board belum dikonfigurasi!"}), 400

    all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
    
    tabel_control = []
    tabel_sensor = []

    for w in all_widgets:
      # Ambil data mapping (GPIO & Channel) jika widget sudah di-mapping
      channel_idx = w.mapping.channel_index if w.mapping else -1
      gpio_pin = w.mapping.gpio_pin if w.mapping else -1
      
      # Struktur dasar setiap node/komponen
      widget_data = {
          "name": w.label_name,
          "type": w.widget_type,
          "gpio": gpio_pin,
          "zone": w.zone_name if hasattr(w, 'zone_name') else 'Area Umum'
      }

      # Pisahkan berdasarkan Tipe (Sensor vs Control)
      if w.widget_type.startswith('SENSOR_'):
          tabel_sensor.append(widget_data)
      else:
          # Jika Control/Output, tambahkan parameter channel relay
          widget_data["channel"] = channel_idx
          tabel_control.append(widget_data)

    # Urutkan tabel_control berdasarkan urutan channel relay agar rapi dibaca firmware
    tabel_control = sorted(tabel_control, key=lambda x: x.get('channel', 0))

    # Bentuk akhir JSON Tree yang simpel
    master_json = {
        "hardware_node": {
            "board_id": board.device_id,
            "controller": board.board_name
        },
        "monitoring": {
            "tabel_control": tabel_control,
            "tabel_sensor": tabel_sensor
        }
    }

    # Simpan history generate ke SQLite
    proj.generated_json = json.dumps(master_json)
    proj.updated_at = int(time.time())
    db.session.commit()
    
    return jsonify(master_json), 200
  except Exception as e:
    return jsonify({"status": "error", "message": f"Gagal mengompilasi JSON: {str(e)}"}), 500

@app.route('/studio/<int:project_id>')
@login_required
def open_studio(project_id):
  proj = Project.query.get_or_404(project_id)
  board = ControllerBoard.query.filter_by(project_id=proj.id).first()
  fb_list = FunctionBlock.query.filter_by(board_id=board.id).all() if board else []
  widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
  rules = AutomationRule.query.filter_by(project_id=proj.id).all()

  widgets_data = []
  for w in widgets:
    icons_map = {
        'LAMP_INDICATOR': '💡', 'PUMP_CONTROL': '💧', 'GATE_CONTROL': '🚪',
        'FAN_CONTROL': '🌀', 'SMART_PLUG': '🔌', 'SENSOR_FIRE': '🔥',
        'SENSOR_GAS': '💨', 'SENSOR_PIR': '🏃', 'SENSOR_TEMP': '🌡️', 'SENSOR_POWER': '⚡'
    }
    icon_str = icons_map.get(w.widget_type, '◉')
    widgets_data.append({
        "id": f"w_{w.id}",
        "widget_id": w.widget_id,
        "label_name": w.label_name,
        "zone_name": w.zone_name if hasattr(w, 'zone_name') else 'Area Umum',
        "widget_type": w.widget_type,
        "pos_x": w.pos_x,
        "pos_y": w.pos_y,
        "icon": icon_str,
        "mapping": {
            "channel_index": w.mapping.channel_index if w.mapping else 0,
            "gpio_pin": w.mapping.gpio_pin if w.mapping else 23,
            "active_low": w.mapping.active_low if (w.mapping and hasattr(w.mapping, 'active_low')) else False,
        },
    })

  return render_template(
      'studio.html',
      project=proj, board=board, function_blocks=fb_list,
      widgets_json=json.dumps(widgets_data),
      rules=rules
  )

@app.route('/api/upload_denah/<int:project_id>', methods=['POST'])
def upload_denah(project_id):
  try:
    if 'file' not in request.files: return jsonify({"status": "error", "message": "Tidak ada file yang dipilih!"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "Nama file tidak boleh kosong!"}), 400

    custom_label = request.form.get('label', 'Denah Custom').strip().replace(' ', '_').replace('/', '_')
    if not custom_label: custom_label = "Denah_Custom"

    allowed_ext = {'png', 'jpg', 'jpeg', 'webp', 'svg'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext: return jsonify({"status": "error", "message": "Format tidak didukung! Gunakan PNG, JPG, WEBP, atau SVG."}), 400

    filename = secure_filename(f"denah_project_{project_id}_{custom_label}_{int(time.time())}.{ext}")
    upload_folder = os.path.join(basedir, 'static', 'images')
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    image_url = f"/static/images/{filename}"
    proj = Project.query.get_or_404(project_id)
    proj.background_image = image_url
    db.session.commit()

    return jsonify({"status": "success", "message": "Denah berhasil diunggah!", "url": image_url, "label": request.form.get('label', 'Denah Custom').strip()}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/delete_denah/<int:project_id>', methods=['DELETE', 'POST'])
def delete_denah(project_id):
  try:
    proj = Project.query.get_or_404(project_id)
    current_img = proj.background_image

    if current_img and current_img.startswith('/static/images/denah_project_'):
      filename = current_img.split('/')[-1]
      file_path = os.path.join(basedir, 'static', 'images', filename)
      if os.path.exists(file_path):
        try: os.remove(file_path)
        except Exception as e: print(f"[SERVER] Gagal menghapus file fisik: {e}")

    default_url = "/static/images/denah_rumah.png"
    proj.background_image = default_url
    db.session.commit()

    return jsonify({"status": "success", "message": "Denah kustom berhasil dihapus. Kembali ke default.", "url": default_url}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/seed_test')
def seed_test_project():
  try:
    Project.query.delete()
    proj = Project(name="Smart Home Lantai 1", domain_type="smarthome")
    db.session.add(proj)
    db.session.commit()
    return jsonify({"status": "success", "message": "Silakan atur manual di Studio.", "project_id": proj.id}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
@login_required
def dashboard():
  proj = Project.query.first()
  widgets = WidgetNode.query.filter_by(project_id=proj.id).all() if proj else []

  widgets_data = []
  # Tambahkan kamus ikon ini
  icons_map = {
      'LAMP_INDICATOR': '💡', 'PUMP_CONTROL': '💧', 'GATE_CONTROL': '🚪',
      'FAN_CONTROL': '🌀', 'SMART_PLUG': '🔌', 'SENSOR_FIRE': '🔥',
      'SENSOR_GAS': '💨', 'SENSOR_PIR': '🏃', 'SENSOR_TEMP': '🌡️', 'SENSOR_POWER': '⚡'
  }
  
  for w in widgets:
    # Ambil ikon dari kamus, jika tidak ada gunakan '◉'
    icon_str = icons_map.get(w.widget_type, '◉')
    
    widgets_data.append({
        'id': f'w_{w.id}', 'widget_id': w.widget_id, 'label_name': w.label_name,
        'zone_name': w.zone_name if hasattr(w, 'zone_name') else 'Area Umum',
        'widget_type': w.widget_type, 'icon': icon_str,
        'mapping': {'channel_index': w.mapping.channel_index if w.mapping else 0, 'gpio_pin': w.mapping.gpio_pin if w.mapping else 23},
    })

  return render_template('index.html', project=proj, widgets=widgets, widgets_json=json.dumps(widgets_data))

@socketio.on('connect')
def handle_web_connect():
  if last_known_status: socketio.emit('update_status', get_web_payload(last_known_status))

@socketio.on('trigger_emergency')
def handle_web_emergency(data):
  global last_known_alarms, virtual_state, WS_LOOP
  last_known_alarms["fire"] = True
  if "alarm" in virtual_state: virtual_state["alarm"]["fire"] = True
  socketio.emit('alarm_update', last_known_alarms)
  alarm_payload = last_known_alarms.copy()
  alarm_payload["location"] = "Bedroom"
  msg_str = json.dumps({"type": "alarm_update", "from": "panel01", "to": "all", "timestamp": int(time.time()), "payload": alarm_payload})
  try:
    if WS_LOOP and WS_LOOP.is_running():
      for d_id, ws in list(connected_devices.items()): asyncio.run_coroutine_threadsafe(ws.send(msg_str), WS_LOOP)
  except Exception as e:
    print(f"[ERROR] Emergency trigger gagal: {e}")

@socketio.on('alarm_ack_web')
def handle_web_ack(data):
  alarm_name = data.get("alarm", "")
  global last_known_alarms, virtual_state, WS_LOOP
  if alarm_name in last_known_alarms: last_known_alarms[alarm_name] = False
  if "alarm" in virtual_state and alarm_name in virtual_state["alarm"]: virtual_state["alarm"][alarm_name] = False
  socketio.emit('update_status', get_web_payload(virtual_state))
  socketio.emit('alarm_update', last_known_alarms)
  clear_payload = last_known_alarms.copy()
  clear_payload["location"] = "Aman"
  msg_str = json.dumps({"type": "alarm_update", "from": "panel01", "to": "all", "timestamp": int(time.time()), "payload": clear_payload})
  try:
    if WS_LOOP and WS_LOOP.is_running():
      for d_id, ws in list(connected_devices.items()): asyncio.run_coroutine_threadsafe(ws.send(msg_str), WS_LOOP)
  except Exception as e:
    print(f"[ERROR] Clear alarm gagal: {e}")

@socketio.on('control_gate')
def handle_gate_control(data):
    handle_general_relay(data)

@socketio.on('control_relay')
def handle_general_relay(data):
    device = data.get('device', 'unknown') # Contoh: 'relay_1'
    state_action = data.get('state', 'TOGGLE')
    
    # Ekstrak nomor channel dari string
    try:
        channel = int(device.split('_')[1])
    except:
        channel = 0

    global virtual_state
    if state_action == 'TOGGLE':
        current_state = virtual_state["relay"][channel]
        new_state = not current_state
    else:
        new_state = bool(state_action)

    # 1. Update State Internal Server & Sinkronkan ke Web UI
    virtual_state["relay"][channel] = new_state
    socketio.emit('update_status', get_web_payload(virtual_state))

    # 2. Cari nama variabel (label_name) dari database untuk Pager
    var_name = f"relay_{channel}" # Fallback
    with app.app_context():
        proj = Project.query.first()
        if proj:
            widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
            for w in widgets:
                # Cari widget mana yang menggunakan channel ini
                if w.mapping and w.mapping.channel_index == channel:
                    var_name = w.label_name
                    break

    # 3. Rakit Payload untuk Pager (UI Aplikasi Mobile/Pager)
    msg_to_pager = json.dumps({
        "type": "status_update", 
        "from": "server", 
        "to": "all",
        "payload": {"variable": var_name, "value": new_state}
    })

    # 4. Rakit Payload untuk Main Panel ESP32 Fajar (Hardware)
    payload_to_esp = json.dumps({
        "type": "hardware_command",
        "target": "main_panel_01",
        "payload": {
            "slave_id": 1,
            "module_type": "RELAY_8CH",
            "channel": channel,
            "state": new_state
        }
    })

    # 5. Tembakkan ke Hardware & Pager via Raw WebSocket
    global WS_LOOP
    if WS_LOOP and WS_LOOP.is_running() and connected_devices:
        for d_id, ws in list(connected_devices.items()):
            # Kirim perintah fisik ke ESP32
            if d_id.startswith("main_panel") or d_id.startswith("panel"):
                asyncio.run_coroutine_threadsafe(ws.send(payload_to_esp), WS_LOOP)
                print(f"\033[95m[OUTBOUND] 🕹️ Command dikirim ke {d_id} | Channel {channel} = {'ON' if new_state else 'OFF'}\033[0m")
            
            # Kirim update visual ke Pager
            elif d_id.startswith("pager"):
                asyncio.run_coroutine_threadsafe(ws.send(msg_to_pager), WS_LOOP)

# ──────────────────────────────────────────────
# Router WebSocket SCS v1.0 & Task
# ──────────────────────────────────────────────
async def router_handler(websocket, *args):
  global REAL_PANEL_CONNECTED, virtual_state, last_known_status
  device_id = "unknown"
  client_ip = websocket.remote_address[0] if websocket.remote_address else "local"

  try:
    async for message in websocket:
      try:
        data = json.loads(message)
        msg_type = data.get("type", "unknown")
        sender = data.get("from", "unknown")
        target = data.get("to", "unknown")
        payload = data.get("payload", {})

        if sender != "unknown" and sender not in connected_devices:
            device_id = sender
            connected_devices[device_id] = websocket
            print(f"\033[92m[WS-8765] 🔗 Auto-Register jalur koneksi: {device_id}\033[0m")

        if msg_type.lower() not in ["field_data", "heartbeat", "slave_heartbeat"]:
            print(f"\n[WS-8765] 📨 INCOMING dari [{sender}] -> ke [{target}] | Tipe: {msg_type.upper()}")
            if payload: print(f"         ↳ Payload: {json.dumps(payload)}")

        if msg_type == "hello":
          device_id = sender
          connected_devices[device_id] = websocket
          print(f"[WS-8765] 🟢 Handshake sukses! Perangkat terdaftar: {device_id} ({client_ip})")
          if sender.startswith("panel"):
            REAL_PANEL_CONNECTED = True
            print("[WS-8765] ⚡ HARDWARE PANEL ASLI TERHUBUNG! Mengambil alih dari Virtual Panel.")

          await websocket.send(json.dumps({
              "type": "hello_ack", "from": "server", "to": device_id,
              "timestamp": int(time.time()), "payload": {"result": "success"},
          }))

          # PUSH DUA JALUR TERPISAH (Relay & Sensor Manifest) TANPA HARDCODE DUMMY
          if sender.startswith("pager"):
            with app.app_context():
              proj = Project.query.first()
              all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all() if proj else []
              
              relay_items = []
              sensor_pages = []
              
              for idx, w in enumerate(all_widgets):
                  if w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
                      is_on = virtual_state["relay"][idx] if idx < len(virtual_state["relay"]) else False
                      relay_items.append({"variable": w.label_name, "value": is_on})
                  elif w.widget_type.startswith('SENSOR_'):
                      sensor_pages.append({
                          "page_id": f"env_{w.label_name}",
                          "sensor_type": w.widget_type,
                          "title": w.zone_name.upper() if w.zone_name else "AREA UMUM"
                      })

              msg_relay = json.dumps({"type": "runtime_list", "from": "server", "to": device_id, "payload": {"relay": relay_items}})
              msg_sensor = json.dumps({"type": "runtime_sensor_manifest", 
                                       "from": "server", 
                                       "to": device_id, 
                                       "payload": {"sensor_pages": sensor_pages}})

              await websocket.send(msg_relay)
              await websocket.send(msg_sensor)
              print(f"[WS-8765] 📤 [POC] Push murni dari DB: Relay ({len(relay_items)} item) & Sensor Manifest ({len(sensor_pages)} page) ke {device_id}")
              
        # =========================================================
        # 1. INBOUND / ETL EXTRACTION & LOAD (Dari Main Panel)
        # =========================================================
        elif msg_type.lower() == "field_data" or target == "unknown":

            if not REAL_PANEL_CONNECTED:
                REAL_PANEL_CONNECTED = True
                print("\033[93m[SERVER] ⚡ HARDWARE ASLI TERDETEKSI! Mematikan Virtual Panel...\033[0m")
            inner_type = payload.get("type", "unknown")
            slave_id = payload.get("slave_id", "N/A")
            
            # A. Tangani Handshake "Hello"
            if inner_type == "hello":
                slave_uid = payload.get("slave_uid", "Unknown")
                fw_version = payload.get("fw", "1.0.0")
                print(f"[MIDDLEWARE] 👋 Main Panel / Slave Terdaftar: {slave_uid} (FW: {fw_version})")
                continue
                
            # B. Tangani "Heartbeat" (Gunakan warna abu-abu agar tidak mencolok)
            elif inner_type == "heartbeat":
                print(f"\033[90m[WS] 💓 Heartbeat dari Slave {slave_id} (Online)\033[0m")
                continue
                
            # C. Tangani Data Sensor (etl_data) dengan Warna Cyan dan Hijaux
            elif inner_type == "etl_data":
                instance_id = payload.get("instance_id", "unknown_instance")
                sensor_type = payload.get("sensor_type", "UNKNOWN")
                values = payload.get("payload", {})
                
                print(f"\033[96m[ETL] 📥 Slave {slave_id} | Instance: {instance_id} ({sensor_type})\033[0m")
                
                # --- SUNTIKAN DINAMIS UNTUK ST ENGINE ---
                # Apapun sensor baru yang dirakit Fajar, ambil nilai parameternya secara otomatis
                if values:
                    # Prioritaskan key 'raw' atau 'value' jika ada
                    if "raw" in values:
                        RUNTIME_REGISTRY[instance_id] = values["raw"]
                    else:
                        # Jika tidak ada, "rampas" nilai pertama dari dictionary JSON yang dikirim ESP32
                        first_key = list(values.keys())[0]
                        RUNTIME_REGISTRY[instance_id] = values[first_key]

                for key, val in values.items():
                    var_name = f"{instance_id}_{key}"
                    RUNTIME_REGISTRY[var_name] = val
                    print(f"   ├─ \033[92m{var_name}\033[0m = {val}")

                # 2. Sinkronisasi ke Web Dashboard HMI
                if "temperature" in values:
                    virtual_state["environment"]["temperature"] = values["temperature"]
                if "humidity" in values:
                    virtual_state["environment"]["humidity"] = values["humidity"]
                
                # --- PERBAIKAN SENSOR GAS ---
                # Tangkap dari key "raw" (kiriman ESP32) atau "gas_ppm"
                if "raw" in values:
                    virtual_state["environment"]["gas_ppm"] = values["raw"]
                elif "gas_ppm" in values:
                    virtual_state["environment"]["gas_ppm"] = values["gas_ppm"]
                # ----------------------------
                

                if "voltage" in values:
                    virtual_state["power"]["voltage"] = values["voltage"]
                if "power" in values:
                    virtual_state["power"]["power"] = values["power"]
                    
                last_known_status = virtual_state
                socketio.emit("update_status", get_web_payload(last_known_status))

                # =========================================================
                # 3. SINKRONISASI KE PAGER (Aplikasi Mobile)
                # ========================================================
                pager_data = values.copy()
                if "raw" in pager_data and sensor_type == "MQ_ANALOG":
                    pager_data["gas_ppm"] = pager_data.pop("raw") 
                
                msg_pager = json.dumps({
                    "type": "sensor_update",
                    "from": "server",
                    "to": "all",
                    "payload": {
                        "page_id": f"env_{instance_id}",
                        "data": pager_data
                    }
                })
                
                global WS_LOOP
                if WS_LOOP and WS_LOOP.is_running():
                    for d_id, ws in list(connected_devices.items()):
                        if d_id.startswith("pager"):
                            asyncio.run_coroutine_threadsafe(ws.send(msg_pager), WS_LOOP)
               

        # =========================================================
        # 2. OUTBOUND / COMMAND DISPATCHER (Dari Pager / ST Engine)
        # =========================================================
        elif msg_type == "command" and target == "server":
            var_name = payload.get("variable")
            target_val = payload.get("value")

            print(f"\n[MIDDLEWARE] 🕹️ Menerima command logika: '{var_name}' -> {target_val}")

            # 1. Update Runtime Registry agar state tersinkronisasi
            RUNTIME_REGISTRY[var_name] = target_val

            channel_idx = None # <-- Menyiapkan variabel penampung channel

            # Update Virtual State untuk sinkronisasi Web HMI
            with app.app_context():
                proj = Project.query.first()
                w = WidgetNode.query.filter_by(label_name=var_name).first() if proj else None
                if w and w.mapping:
                    channel_idx = w.mapping.channel_index # <-- Ambil channel dari SQLite
                    if channel_idx < len(virtual_state["relay"]): 
                        virtual_state["relay"][channel_idx] = target_val
                else:
                    names = ["ruang_tamu", "kamar", "dapur", "garasi"]
                    if var_name in names: virtual_state["relay"][names.index(var_name)] = target_val

            last_known_status = virtual_state
            socketio.emit("update_status", get_web_payload(last_known_status))

            # Broadcast ke Pager agar indikator switch berubah
            event_push_msg = json.dumps({
                "type": "status_update", "from": "server", "to": "all",
                "payload": {"variable": var_name, "value": target_val},
            })
            for d_id, ws in list(connected_devices.items()):
                try: await ws.send(event_push_msg)
                except: pass
            print(f"[WS-8765] ⚡ [POC EVENT-PUSH] Disiarkan status_update: {var_name}={target_val}")

            # 2. THE MISSING LINK FIX: Dispatch Dinamis ke Hardware
            if channel_idx is not None:
                # Merakit JSON sesuai standar instruksi aktuator fisik di Slave 1
                cmd_payload = json.dumps({
                    "type": "hardware_command",
                    "target": "main_panel_01",
                    "payload": {
                        "slave_id": 1,
                        "module_type": "RELAY_8CH",
                        "channel": channel_idx,
                        "state": target_val
                    }
                })

                # Dispatch (Kirim) perintah ke ESP32
                for d_id, ws in list(connected_devices.items()):
                    if d_id.startswith("main_panel") or d_id.startswith("panel"):
                        try:
                            await ws.send(cmd_payload)
                            print(f"  ↳ 📤 Dispatch ke Hardware: Slave 1, Ch {channel_idx}")
                        except:
                            print(f"  ↳ ❌ Gagal Dispatch: Main Panel terputus!")
            else:
                print(f"  ↳ ⚠️ Command diabaikan: Variabel '{var_name}' belum di-mapping di SH Studio.")


        elif target == "all":
          for d_id, ws in list(connected_devices.items()):
            if d_id != sender:
              try: await ws.send(message)
              except: pass
          if msg_type == "status" and sender.startswith("panel"):
            last_known_status = payload
            socketio.emit("update_status", get_web_payload(last_known_status))
            current_alarms = last_known_status.get("alarm", {})
            global last_known_alarms
            if current_alarms != last_known_alarms:
              last_known_alarms = current_alarms.copy()
              alarm_payload = current_alarms.copy()
              alarm_payload["location"] = get_alarm_location(current_alarms)
              broadcast_str = json.dumps({
                  "type": "alarm_update", "from": "panel01", "to": "all",
                  "timestamp": int(time.time()), "payload": alarm_payload,
              })
              for d_id, ws in list(connected_devices.items()):
                if d_id != sender:
                  try: await ws.send(broadcast_str)
                  except: pass
              socketio.emit("alarm_update", current_alarms)

        elif target == "server" and msg_type == "alarm_ack":
          alarm_name = payload.get("alarm", "unknown")
          print(f"[WS-8765] 🔕 ACK ALARM diproses dari {sender} untuk alarm: {alarm_name}")
          if alarm_name in last_known_alarms: last_known_alarms[alarm_name] = False
          if "alarm" in virtual_state and alarm_name in virtual_state["alarm"]: virtual_state["alarm"][alarm_name] = False
          await connected_devices[sender].send(json.dumps({
              "type": "command_ack", "from": "server", "to": sender,
              "payload": {"command": "alarm_ack", "result": "success"},
          }))
          last_known_status = virtual_state
          socketio.emit("update_status", get_web_payload(last_known_status))
          clear_payload = last_known_alarms.copy()
          clear_payload["location"] = "Aman"
          broadcast_str = json.dumps({
              "type": "alarm_update", "from": "panel01", "to": "all",
              "timestamp": int(time.time()), "payload": clear_payload,
          })
          for d_id, ws in list(connected_devices.items()):
            if d_id != sender:
              try: await ws.send(broadcast_str)
              except: pass

        elif not REAL_PANEL_CONNECTED and target == "server":
          state_changed = False
          if msg_type == "relay_toggle":
            idx = payload.get("relay", 0)
            print(f"[WS-8765] 💡 EKSEKUSI: Toggle Relay Ch-{idx} perintah dari {sender} (Mode Virtual)")
            if 0 <= idx < len(virtual_state["relay"]):
              virtual_state["relay"][idx] = not virtual_state["relay"][idx]
              state_changed = True
          elif msg_type == "gate_open":
            print(f"[WS-8765] 🚪 EKSEKUSI: Membuka Gerbang perintah dari {sender}")
            virtual_state["alarm"]["door"] = True
            state_changed = True
          elif msg_type == "gate_close":
            print(f"[WS-8765] 🚪 EKSEKUSI: Menutup Gerbang perintah dari {sender}")
            virtual_state["alarm"]["door"] = False
            state_changed = True

          if state_changed:
            last_known_status = virtual_state
            socketio.emit("update_status", get_web_payload(last_known_status))
            broadcast_msg = json.dumps({
                "type": "status", "from": "panel01", "to": "all",
                "timestamp": int(time.time()), "payload": virtual_state,
            })
            for d_id, ws in list(connected_devices.items()):
              try: await ws.send(broadcast_msg)
              except: pass

        elif target in connected_devices:
          print(f"[WS-8765] 🔀 ROUTING: Meneruskan pesan langsung ke [{target}]")
          await connected_devices[target].send(message)
        else:
          print(f"[WS-8765] ⚠️ PERINGATAN: Target [{target}] tidak ditemukan dalam daftar perangkat online!")

      except json.JSONDecodeError:
        print(f"[WS-8765] ❌ Error: Menerima paket non-JSON dari {client_ip}")
  except websockets.exceptions.ConnectionClosed:
    pass
  finally:
    if device_id in connected_devices: del connected_devices[device_id]
    print(f"[WS-8765] 🔴 Perangkat terputus dari server: {device_id}")

async def run_ws_server():
  global WS_LOOP
  WS_LOOP = asyncio.get_running_loop()
  print("[SERVER] SCS v1.0 Router siap di ws://0.0.0.0:8765")
  await websockets.serve(router_handler, "192.168.88.254", 8765, ping_interval=None)
  asyncio.create_task(virtual_panel_task())
  asyncio.create_task(st_engine_task())
  await asyncio.Future()

def start_raw_websocket_server():
  asyncio.run(run_ws_server())

if __name__ == '__main__':
  threading.Thread(target=start_raw_websocket_server, daemon=True).start()
  print("=" * 60)
  print("  Smart Home Router SCS v1.0 + Virtual Panel")
  print("=" * 60)
  socketio.run(app, host='192.168.88.254', port=5000, debug=False, use_reloader=False)