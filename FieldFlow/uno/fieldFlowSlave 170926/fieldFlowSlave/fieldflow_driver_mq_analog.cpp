#include "fieldflow_driver_mq_analog.h"

#include <Arduino.h>

MQAnalogDriver::MQAnalogDriver()
: _pin(34)
{
}

bool MQAnalogDriver::begin(uint8_t pin)
{
    _pin = pin;

    pinMode(_pin, INPUT);

    return true;
}

bool MQAnalogDriver::read(JsonObject payload)
{
    int raw = analogRead(_pin);

    payload["raw"] = raw;

    return true;
}

const char* MQAnalogDriver::type()
{
    return "MQ_ANALOG";
}