#include "fieldflow_port_map.h"
#include "fieldflow_logger.h"

// =======================================================
// PORT MAPPING ESP32-S3 FIELD FLOW SLAVE
// Berdasarkan PCB Final Rev-1
// =======================================================

uint8_t fieldflowResolvePort(const String &port)
{
    // ===============================
    // DIGITAL IO
    // ===============================
    if(port == "NIO1")   return 35;
    if(port == "NIO2")   return 36;
    if(port == "NIO3")   return 37;
    if(port == "NIO4")   return 38;
    if(port == "NIO5")   return 39;
    if(port == "NIO6")   return 40;
    if(port == "NIO7")   return 41;
    if(port == "NIO8")   return 42;

    if(port == "AI1")   return 1;
    if(port == "AI2")   return 2;
    if(port == "AI3")   return 3;
    if(port == "AI4")   return 7;

    if(port == "I2C_SCL")   return 9;
    if(port == "I2C_SDA")   return 8;
    if(port == "UART_RX")   return 18;
    if(port == "UART_TX")   return 17;





   
   
   
   
   
   
   
   
   
   
   

    fieldflowLogWarn(("INVALID PORT : " + port).c_str());
    return 255;
}