#include "fieldflow_relay_adapter.h"
#include "fieldflow_logger.h"
#include "fieldflow_driver_factory.h"
#include "fieldflow_port_map.h"

RelayRuntime relayRegistry[MAX_RUNTIME_RELAYS];
uint8_t relayCount = 0;

//--------------------------------------------------
// CLEAR REGISTRY
//--------------------------------------------------
void relayRuntimeClear()
{
    for(uint8_t i=0;i<relayCount;i++)
    {
        bool offLevel =
            relayRegistry[i].activeHigh ? LOW : HIGH;

        digitalWrite(relayRegistry[i].gpio, offLevel);
    }

    relayCount = 0;

    fieldflowLogInfo("Relay registry cleared");
}

//--------------------------------------------------
// LOAD MANIFEST
//--------------------------------------------------
void relayRuntimeLoad(JsonArray actuatorArray)
{
    Serial.print("[INFO ] Relay registry cleared\n");
    Serial.print("[INFO ] Incoming Relay = ");
    Serial.println(actuatorArray.size());







    relayRuntimeClear();

    for(JsonObject item : actuatorArray)
    {
        if(relayCount >= MAX_RUNTIME_RELAYS)
            break;

        RelayRuntime &r = relayRegistry[relayCount];

        // Identitas runtime
        r.instanceId = item["instance_id"] | "";
        r.title      = item["instance_id"] | "";

        // Mapping channel & GPIO
        r.channel = item["channel"] | relayCount;

        String port = item["port"] | "";
        r.gpio = fieldflowResolvePort(port);

        // Active level dari middleware
        r.activeHigh = (item["active_level"] | 1) == 1;

        // Initial state
        r.state = item["initial_state"] | false;
        r.enabled = true;

        // Debug mapping
        Serial.print("[MAP ] ");
        Serial.print(port);
        Serial.print(" -> GPIO ");
        Serial.println(r.gpio);

        // Validasi GPIO
        if(r.gpio == 255)
        {
            Serial.print("[WARN] INVALID PORT : ");
            Serial.println(port);
            continue;
        }

        pinMode(r.gpio, OUTPUT);

        bool level = r.activeHigh ? r.state : !r.state;
        digitalWrite(r.gpio, level);

        Serial.print("[RELAY] ");
        Serial.print(r.instanceId);
        Serial.print(" GPIO=");
        Serial.print(r.gpio);
        Serial.print(" CH=");
        Serial.print(r.channel);
        Serial.print(" ACTIVE=");
        Serial.print(r.activeHigh ? "HIGH" : "LOW");
        Serial.print(" STATE=");
        Serial.println(r.state ? "ON" : "OFF");

        relayCount++;
    }

    fieldflowLogInfo("Runtime Relay Loaded");
}
//--------------------------------------------------
// FIND RELAY
//--------------------------------------------------
int relayRuntimeFind(const String &instanceId)
{
    for(uint8_t i=0;i<relayCount;i++)
    {
        if(relayRegistry[i].instanceId == instanceId)
            return i;
    }

    return -1;
}

//--------------------------------------------------
// EXECUTE RELAY
//--------------------------------------------------
bool relayRuntimeExecute(const String &instanceId, bool value)
{
    int idx = relayRuntimeFind(instanceId);

    if(idx < 0)
        return false;

    RelayRuntime &r = relayRegistry[idx];

    r.state = value;

    bool gpioLevel = r.activeHigh ? value : !value;

    digitalWrite(r.gpio, gpioLevel);

    if(fieldflowDebugEnabled())
    {
        fieldflowLogDebug(
            "Relay " + instanceId +
            " = " + String(value ? "ON":"OFF")
        );
    }

    return true;
}

//--------------------------------------------------
// CREATE ACK JSON
//--------------------------------------------------
String relayRuntimeCreateAck(const String &instanceId)
{
    StaticJsonDocument<256> doc;

    int idx = relayRuntimeFind(instanceId);

    if(idx < 0)
        return "";

    RelayRuntime &r = relayRegistry[idx];

    doc["type"] = "relay_ack";
    doc["from"] = "panel01";
    doc["to"]   = "server";

    JsonObject payload = doc.createNestedObject("payload");

    payload["instance_id"] = r.instanceId;
    payload["gpio"] = r.gpio;
    payload["state"] = r.state;

    String json;
    serializeJson(doc,json);

    return json;
}
bool relayRuntimeSetChannel(uint8_t channel, bool state)
{
    for(uint8_t i=0;i<relayCount;i++)
    {
        if(relayRegistry[i].channel != channel)
            continue;

        relayRegistry[i].state = state;

        bool level = relayRegistry[i].activeHigh ? state : !state;

        digitalWrite(relayRegistry[i].gpio, level);

        Serial.printf("[RELAY CH%d] %s -> %s\n",
                      channel,
                      relayRegistry[i].instanceId.c_str(),
                      state ? "ON" : "OFF");

        return true;
    }

    fieldflowLogWarn("CHANNEL NOT FOUND");
    return false;
}