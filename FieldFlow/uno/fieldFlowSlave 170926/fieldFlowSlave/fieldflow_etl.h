#ifndef FIELDFLOW_ETL_H
#define FIELDFLOW_ETL_H

#include <ArduinoJson.h>
#include <Arduino.h>

bool fieldflowPublishETL(const String& instanceId,
                         const String& sensorType,
                         JsonObject payload);

#endif