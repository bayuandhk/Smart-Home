#ifndef FIELDFLOW_DRIVER_BASE_H
#define FIELDFLOW_DRIVER_BASE_H

#include <Arduino.h>
#include <ArduinoJson.h>

class FieldFlowDriverBase
{
public:
    virtual ~FieldFlowDriverBase() {}

    virtual bool begin(uint8_t pin) = 0;

    virtual bool read(JsonObject out) = 0;

    virtual const char* type() = 0;
};

#endif