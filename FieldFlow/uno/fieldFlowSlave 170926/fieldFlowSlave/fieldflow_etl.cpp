#include "fieldflow_etl.h"
#include "fieldflow_tcp_bus.h"

bool fieldflowPublishETL(const String& instanceId,
                         const String& sensorType,
                         JsonObject payload)
{
    StaticJsonDocument<512> doc;

    doc["type"]        = "etl_data";
    doc["slave_id"]    = 1;
    doc["instance_id"] = instanceId;
    doc["sensor_type"] = sensorType;

    JsonObject outPayload =
        doc.createNestedObject("payload");

    for(JsonPair kv : payload)
    {
        outPayload[kv.key()] = kv.value();
    }

    String json;
    serializeJson(doc, json);

    return fieldflowTcpPublish(json);
}