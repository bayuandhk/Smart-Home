from edge_server.slave_manager import slave_manager
import json

class Router:
    def __init__(self):
        self.ws_server = None

    def set_ws_server(self, ws_server):
        """Bind WebSocket Server ke Router."""
        self.ws_server = ws_server

    async def handle_from_slave(self, slave_uid, message):
        """
        Diterima dari TCP Slave, teruskan ke Browser/HMI.
        """
        msg_type = message.get("type")
        
        # Logika dari tcp_server (sebelumnya di app.py) dipindahkan ke sini
        if msg_type in ["etl_data", "relay_ack", "runtime_manifest_ack"]:
            # Teruskan ke HMI (web dashboard)
            if self.ws_server:
                await self.ws_server.forward_etl_to_hmi(slave_uid, message)
                
        elif msg_type == "heartbeat":
            # Jika perlu bisa di broadcast ke UI
            pass

            
    async def handle_from_hmi(self, message):
        """
        Diterima dari Browser/HMI via WebSocket, teruskan ke TCP Slave.
        Misalnya perintah relay (hardware_command), runtime_manifest, dll.
        """
        msg_type = message.get("type")
        
        # Cari target spesifik jika ada (bisa di root message atau di payload)
        payload = message.get("payload", {})
        target_slave_id = message.get("slave_id")
        if target_slave_id is None and isinstance(payload, dict):
            target_slave_id = payload.get("slave_id")
        
        # Cari UID berdasarkan ID jika diperlukan (slave_manager menggunakan UID sbg key)
        target_uid = None
        if target_slave_id is not None:
            for uid, info in slave_manager.slaves.items():
                if str(info.get("slave_id")) == str(target_slave_id):
                    target_uid = uid
                    break


        
        if msg_type in ["runtime_manifest", "command", "hardware_command"]:
            if target_uid:
                print(f"[Router] Meneruskan {msg_type} ke Slave {target_uid}")
                await slave_manager.send_to_slave(target_uid, message)
            else:
                # Jika tidak spesifik, kirim ke semua slave (atau default slave 1)
                print(f"[Router] Broadcast {msg_type} ke semua Slave")
                await slave_manager.broadcast(message)

router = Router()
