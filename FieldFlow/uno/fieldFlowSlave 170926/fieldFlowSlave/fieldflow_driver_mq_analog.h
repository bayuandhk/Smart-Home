#ifndef FIELDFLOW_DRIVER_MQ_ANALOG_H
#define FIELDFLOW_DRIVER_MQ_ANALOG_H

#include "fieldflow_driver_base.h"

class MQAnalogDriver : public FieldFlowDriverBase
{
public:
    MQAnalogDriver();

    bool begin(uint8_t pin) override;

    bool read(JsonObject payload) override;

    const char* type() override;

private:
    uint8_t _pin;
};

#endif