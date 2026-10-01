import asyncio
import threading
import sys
import os

# Memastikan PYTHONPATH benar
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edge_server.tcp_server import start_tcp_server
from edge_server.websocket_server import ws_bridge

# Import the flask app and required properties
from app import app, socketio, get_local_ip
import app as app_module

# Konfigurasi bridge
ws_bridge.set_app_module(app_module)

def run_flask():
    local_ip = get_local_ip()
    print("=" * 60)
    print("  Smart Home Edge Runtime & Web Dashboard")
    print(f"  Web Dashboard (Local)  : http://localhost:5001")
    print(f"  Web Dashboard (Network): http://{local_ip}:5001")
    print(f"  TCP Server untuk Slave : {local_ip}:5000")
    print("=" * 60)
    # Jalankan Flask-SocketIO pada port 5001 (karena TCP port 5000 dipakai Slave)
    socketio.run(app, host="0.0.0.0", port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

async def main():
    print("[EDGE] Memulai Edge Runtime...")
    
    # Expose event loop ke app.py untuk komunikasi asynchronous
    app_module.EDGE_LOOP = asyncio.get_running_loop()
    
    # Start ST Engine yang sebelumnya di-start saat WS connect
    app_module.start_st_engine_task()

    # Flask di background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    # Start TCP Server
    await start_tcp_server()

if __name__ == "__main__":
    asyncio.run(main())
