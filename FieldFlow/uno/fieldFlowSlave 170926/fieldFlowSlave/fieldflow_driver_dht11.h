#ifndef FIELDFLOW_DRIVER_DHT11_H
#define FIELDFLOW_DRIVER_DHT11_H

#include "fieldflow_driver_base.h"
#include <DHT.h>

class FieldFlowDriverDHT11 : public FieldFlowDriverBase
{
public:
    FieldFlowDriverDHT11();

    bool begin(uint8_t pin) override;

    bool read(JsonObject out) override;

    const char* type() override;

private:
    DHT* dht;
    uint8_t pinNumber;
};

#endif