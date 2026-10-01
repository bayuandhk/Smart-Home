#include "fieldflow_system.h"
#include "fieldflow_logger.h"
#include "fieldflow_relay_adapter.h"  
#include "fieldflow_display.h"
#include "fieldflow_system_status.h"

static unsigned long lastHeap = 0;

void setup()
{
    fieldflowSystemBegin();
}

void loop()
{
    serialDebugTask();

    fieldflowSystemLoop();
  
    heapMonitorTask();
    fieldflowSystemStatusLoop();
    fieldflowDisplayLoop();
}

void serialDebugTask()
{
    if(!Serial.available())
        return;

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if(cmd == "1")
    {
        fieldflowSetDebug(true);
        Serial.println("[DEBUG ON]");
    }
    else if(cmd == "0")
    {
        fieldflowSetDebug(false);
        Serial.println("[DEBUG OFF]");
    }
    else if(cmd == "heap")
    {
        Serial.printf("Heap : %u\n", ESP.getFreeHeap());
    }
    else if(cmd == "tcp")
    {
        Serial.println("[TCP] status command belum diimplementasikan.");
    }

    else if(cmd == "relay")
    {
        Serial.println();
        Serial.println("===== RELAY REGISTRY =====");

        for(uint8_t i = 0; i < relayCount; i++)
        {
            Serial.print("[");
            Serial.print(i);
            Serial.print("] ");

            Serial.print(relayRegistry[i].instanceId);

            Serial.print(" GPIO=");
            Serial.print(relayRegistry[i].gpio);

            Serial.print(" CH=");
            Serial.print(relayRegistry[i].channel);

            Serial.print(" ACTIVE=");
            Serial.print(relayRegistry[i].activeHigh ? "HIGH" : "LOW");

            Serial.print(" STATE=");
            Serial.println(relayRegistry[i].state ? "ON" : "OFF");
        }

        Serial.println("==========================");
    }
    else if(cmd == "status")
    {
        Serial.println("========== TCP STATUS ==========");

        Serial.print("ETH     : ");
        Serial.println(systemStatus.ethernetLink ? "UP":"DOWN");

        Serial.print("TCP     : ");
        Serial.println(systemStatus.tcpConnected ? "CONNECTED":"DISCONNECTED");

        Serial.print("Manifest: ");
        Serial.println(systemStatus.manifestVersion);

        Serial.print("TX      : ");
        Serial.println(systemStatus.tcpTxCounter);

        Serial.print("RX      : ");
        Serial.println(systemStatus.tcpRxCounter);

        Serial.print("HB      : ");
        Serial.println(systemStatus.heartbeatCounter);

        Serial.print("Reconnect: ");
        Serial.println(systemStatus.tcpReconnectCounter);

        Serial.println("===============================");
    }
}


void heapMonitorTask()
{
    static unsigned long lastHeap = 0;

    if(millis() - lastHeap < 10000)
        return;

    lastHeap = millis();

    if(fieldflowDebugEnabled())
    {
        Serial.printf("[HEAP] %u\n", ESP.getFreeHeap());
    }
}