#include <ArduinoJson.h>
#include "fieldflow_scheduler.h"
#include "fieldflow_registry.h"
#include "fieldflow_etl.h"
#include "fieldflow_logger.h"
#include "fieldflow_system_status.h"
#include <Arduino.h>

void fieldflowSchedulerBegin()
{
    Serial.println("[INFO ] Scheduler ready");
}

void fieldflowSchedulerLoop()
{
    unsigned long now = millis();

    for(uint8_t i=0;i<FIELD_FLOW_MAX_INSTANCE;i++)
    {
        SensorInstance* inst = fieldflowRegistryGetMutable(i);

        if(inst == nullptr) continue;

        if(now - inst->lastTick >= inst->sampleMs)
        {
            inst->lastTick += inst->sampleMs;

            if(inst->driver != nullptr)
            {
                StaticJsonDocument<128> doc;
                JsonObject obj = doc.to<JsonObject>();

                if(inst->driver->read(obj))
                {
                    static unsigned long lastETLSend = 0;

                    if(millis() - lastETLSend < 20)
                        return;

                    lastETLSend = millis();

                    if(fieldflowDebugEnabled())
                        fieldflowLogDebug("ETL -> " + inst->instanceId);

                    fieldflowPublishETL(
                        inst->instanceId,
                        inst->sensorType,
                        obj
                    );
                    systemStatus.etlCounter++;
                    systemStatus.lastETLMillis = millis();
                }
                else
                {
                    Serial.print("[WARN ] Read failed : ");
                    Serial.println(inst->instanceId);
                }
            }
            else
            {
                Serial.print("[SCHED] ");
                Serial.print(inst->instanceId);
                Serial.println(" no driver");
            }
        }
        
    }
}