import asyncio
import json
from edge_server.slave_manager import slave_manager
from edge_server.router import router
from edge_server.config import TCP_HOST, TCP_PORT

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"\033[94m[TCP Server] Koneksi baru dari Slave pada {addr}\033[0m")
    slave_uid = None

    try:
        while True:
            data = await reader.readline()
            if not data:
                break
            
            raw_str = data.decode('utf-8').strip()
            if not raw_str:
                continue

            try:
                message = json.loads(raw_str)
                msg_type = message.get("type", "unknown")
                
                if msg_type == "hello":
                    slave_uid = message.get("slave_uid", f"UNKNOWN-{addr[1]}")
                    slave_id = message.get("slave_id", 0)
                    slave_manager.register_slave(slave_uid, slave_id, writer)
                    
                    # Balas hello_ack
                    ack = {
                        "type": "hello_ack",
                        "payload": {"result": "success"}
                    }
                    await slave_manager.send_to_slave(slave_uid, ack)

                    # Auto-push manifest langsung ke Slave yang baru connect
                    try:
                        from app import app, generate_hardware_manifests
                        with app.app_context():
                            dep_m, cmd_m = generate_hardware_manifests()
                            if dep_m and dep_m.get("instances"):
                                print(f"[TCP Server] 📤 [AUTO-PUSH] Kirim runtime_manifest ke {slave_uid}")
                                await slave_manager.send_to_slave(slave_uid, dep_m)
                            if cmd_m and cmd_m.get("actuators"):
                                print(f"[TCP Server] 📤 [AUTO-PUSH] Kirim command manifest ke {slave_uid}")
                                await slave_manager.send_to_slave(slave_uid, cmd_m)
                    except Exception as e:
                        print(f"[TCP Server] ⚠️ Gagal auto-push manifest ke {slave_uid}: {e}")

                elif msg_type == "heartbeat":
                    if not slave_uid:
                        # Auto-register jika belum hello
                        slave_uid = f"AUTO-{addr[1]}"
                        slave_id = message.get("slave_id", 0)
                        slave_manager.register_slave(slave_uid, slave_id, writer)
                    print(f"\033[92m[TCP Server] 💓 Heartbeat dari {slave_uid}\033[0m")
                
                # Teruskan message ke Router (untuk diproses lebih lanjut)
                if slave_uid:
                    await router.handle_from_slave(slave_uid, message)
                    
            except json.JSONDecodeError:
                print(f"[TCP Server] Error parsing JSON dari {addr}: {raw_str}")
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[TCP Server] Error dengan koneksi {addr}: {e}")
    finally:
        if slave_uid:
            slave_manager.remove_slave(slave_uid)
        writer.close()
        await writer.wait_closed()
        print(f"\033[93m[TCP Server] Koneksi ditutup dari {addr}\033[0m")

async def start_tcp_server():
    server = await asyncio.start_server(handle_client, TCP_HOST, TCP_PORT)
    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f"[TCP Server] Berjalan pada {addrs}")
    async with server:
        await server.serve_forever()
