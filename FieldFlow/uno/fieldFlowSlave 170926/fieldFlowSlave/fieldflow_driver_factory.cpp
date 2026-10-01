#include "fieldflow_driver_factory.h"

#include "fieldflow_driver_dht11.h"
#include "fieldflow_driver_mq_analog.h"

FieldFlowDriverBase* fieldflowCreateDriver(const String& sensorType,
                                           uint8_t pin)
{
    if(sensorType == "DHT11")
    {
        return new FieldFlowDriverDHT11();
    }

    if(sensorType == "MQ_ANALOG")
    {
        MQAnalogDriver *drv = new MQAnalogDriver();
        drv->begin(pin);
        return drv;
    }

    return nullptr;
}