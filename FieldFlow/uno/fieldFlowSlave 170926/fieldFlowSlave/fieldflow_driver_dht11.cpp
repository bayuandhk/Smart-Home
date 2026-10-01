#include "fieldflow_driver_dht11.h"

FieldFlowDriverDHT11::FieldFlowDriverDHT11()
{
    dht = nullptr;
    pinNumber = 255;
}

bool FieldFlowDriverDHT11::begin(uint8_t pin)
{
    pinNumber = pin;

    dht = new DHT(pinNumber, DHT11);
    dht->begin();

    delay(100);

    return true;
}

bool FieldFlowDriverDHT11::read(JsonObject out)
{
    if(dht == nullptr) return false;

    float t = dht->readTemperature();
    float h = dht->readHumidity();

    if(isnan(t) || isnan(h))
    {
        return false;
    }

    out["temperature"] = t;
    out["humidity"] = h;

    return true;
}

const char* FieldFlowDriverDHT11::type()
{
    return "DHT11";
}