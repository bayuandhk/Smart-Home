#include "fieldflow_manifest.h"

#include "fieldflow_logger.h"
#include "fieldflow_registry.h"
#include "fieldflow_driver_factory.h"
#include "fieldflow_relay_adapter.h"
#include "fieldflow_tcp_bus.h"
#include "fieldflow_port_map.h"
#include "fieldflow_system_status.h"

#include <ArduinoJson.h>

//======================================================
// INIT
//======================================================

void fieldflowManifestBegin()
{
    fieldflowLogInfo("Manifest module ready");
}

//======================================================
// HANDLE MANIFEST JSON
//======================================================

void fieldflowManifestHandle(const String &json)
{
    DynamicJsonDocument doc(4096);

    if(deserializeJson(doc, json) != DeserializationError::Ok)
    {
        fieldflowLogWarn("Manifest JSON invalid");
        return;
    }

    const char *type = doc["type"] | "";

    //==================================================
    // SENSOR MANIFEST (runtime_manifest / deploy_manifest)
    //==================================================
    if(strcmp(type, "runtime_manifest") == 0 || strcmp(type, "deploy_manifest") == 0)
    {
        systemStatus.manifestVersion = doc["version"] | 1;

        fieldflowRegistryClear();

        JsonArray arr = doc["instances"].as<JsonArray>();

        for(JsonObject obj : arr)
        {
            String instanceId = obj["instance_id"] | "";
            String sensorType = obj["sensor_type"] | "";
            String port       = obj["port"] | "";
            uint32_t sampleMs = obj["sample_ms"] | 1000;

            if(fieldflowRegistryAdd(instanceId, sensorType, port, sampleMs))
            {
                uint8_t idx = fieldflowRegistryCount() - 1;
                uint8_t pin = fieldflowResolvePort(port);

                FieldFlowDriverBase *drv = fieldflowCreateDriver(sensorType, pin);

                fieldflowRegistryAttachDriver(idx, drv, pin);

                if(drv)
                    drv->begin(pin);
            }
        }

        fieldflowRegistryPrint();

        DynamicJsonDocument ack(256);
        ack["type"] = "runtime_manifest_ack";
        ack["slave_id"] = 1;
        ack["sensor_count"] = fieldflowRegistryCount();
        ack["relay_count"] = relayCount;

        String out;
        serializeJson(ack, out);
        fieldflowTcpPublish(out);

        return;
    }

    //==================================================
    // ACTUATOR MANIFEST
    //==================================================
    if(strcmp(type, "command") == 0)
    {
        JsonArray actuators = doc["actuators"].as<JsonArray>();

        relayRuntimeLoad(actuators);

        DynamicJsonDocument ack(256);
        ack["type"] = "runtime_manifest_ack";
        ack["slave_id"] = 1;
        ack["sensor_count"] = fieldflowRegistryCount();
        ack["relay_count"] = relayCount;

        String out;
        serializeJson(ack, out);
        fieldflowTcpPublish(out);

        return;
    }

    //==================================================
    // HARDWARE COMMAND
    //==================================================
    if(strcmp(type, "hardware_command") == 0)
    {
        JsonObject payload = doc["payload"];

        String module = payload["module_type"] | "";

        if(module == "RELAY_8CH")
        {
            uint8_t channel = payload["channel"];
            bool state = payload["state"];

            if(relayRuntimeSetChannel(channel, state))
            {
                DynamicJsonDocument ack(256);
                ack["type"] = "relay_ack";
                ack["slave_id"] = 1;
                ack["channel"] = channel;
                ack["state"] = state;

                String out;
                serializeJson(ack, out);
                fieldflowTcpPublish(out);
            }
        }

        return;
    }

    if(fieldflowDebugEnabled())
    {
        fieldflowLogDebug("Unknown Manifest Type : " + String(type));
    }
}