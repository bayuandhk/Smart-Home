#include "fieldflow_registry.h"
#include "fieldflow_logger.h"

static SensorInstance registry[FIELD_FLOW_MAX_INSTANCE];

void fieldflowRegistryBegin()
{
    fieldflowRegistryClear();
    fieldflowLogInfo("Registry ready");
}

void fieldflowRegistryClear()
{
    for(uint8_t i=0;i<FIELD_FLOW_MAX_INSTANCE;i++)
    {
        registry[i].active = false;
        registry[i].instanceId = "";
        registry[i].sensorType = "";
        registry[i].port = "";
        registry[i].sampleMs = 0;
        registry[i].lastTick = 0;
        registry[i].pin = 255;
        registry[i].driver = nullptr;
    }
}

bool fieldflowRegistryAdd(const String& instanceId,
                          const String& sensorType,
                          const String& port,
                          uint32_t sampleMs)
{
    for(uint8_t i=0;i<FIELD_FLOW_MAX_INSTANCE;i++)
    {
        if(!registry[i].active)
        {
            registry[i].active = true;
            registry[i].instanceId = instanceId;
            registry[i].sensorType = sensorType;
            registry[i].port = port;
            registry[i].sampleMs = sampleMs;
            registry[i].lastTick = millis();
            registry[i].pin = 255;
            registry[i].driver = nullptr;
            return true;
        }
    }

    fieldflowLogError("Registry full");
    return false;
}

uint8_t fieldflowRegistryCount()
{
    uint8_t count = 0;

    for(uint8_t i=0;i<FIELD_FLOW_MAX_INSTANCE;i++)
    {
        if(registry[i].active) count++;
    }

    return count;
}

const SensorInstance* fieldflowRegistryGet(uint8_t index)
{
    if(index >= FIELD_FLOW_MAX_INSTANCE) return nullptr;
    if(!registry[index].active) return nullptr;

    return &registry[index];
}

SensorInstance* fieldflowRegistryGetMutable(uint8_t index)
{
    if(index >= FIELD_FLOW_MAX_INSTANCE) return nullptr;
    if(!registry[index].active) return nullptr;

    return &registry[index];
}


bool fieldflowRegistryAttachDriver(uint8_t index,
                                  FieldFlowDriverBase* driver,
                                  uint8_t pin)
{
    if(index >= FIELD_FLOW_MAX_INSTANCE) return false;
    if(!registry[index].active) return false;

    registry[index].driver = driver;
    registry[index].pin = pin;

    return true;
}

void fieldflowRegistryPrint()
{
    Serial.println();
    Serial.println("====== ACTIVE INSTANCE ======");

    Serial.print("Count : ");
    Serial.println(fieldflowRegistryCount());

    for(uint8_t i=0;i<FIELD_FLOW_MAX_INSTANCE;i++)
    {
        if(registry[i].active)
        {
          Serial.print(registry[i].instanceId);
          Serial.print(" -> ");

          Serial.print(registry[i].sensorType);
          Serial.print(" @ ");

          Serial.print(registry[i].port);

          Serial.print(" pin=");
          Serial.print(registry[i].pin);

          Serial.print(" (");

          Serial.print(registry[i].sampleMs);
          Serial.println(" ms)");
        }
    }

    Serial.println("=============================");
}