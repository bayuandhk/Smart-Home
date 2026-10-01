#include "fieldflow_display.h"
#include "fieldflow_system_status.h"

#include <Wire.h>
#include <U8g2lib.h>

static U8G2_SH1106_128X64_NONAME_F_HW_I2C oled(
    U8G2_R0,
    U8X8_PIN_NONE
);

static uint32_t lastRefresh = 0;

void fieldflowDisplayBegin()
{
    // PCB FINAL ESP32-S3
    Wire.begin(8,9);

    oled.begin();
    oled.clearBuffer();

    oled.setFont(u8g2_font_6x12_tf);
    oled.drawStr(10,20,"FIELD FLOW SLAVE");
    oled.drawStr(20,40,"ESP32-S3 READY");

    oled.sendBuffer();
    delay(1000);
}

static void renderHome()
{
    char line[32];

    oled.setFont(u8g2_font_6x12_tf);

    oled.drawStr(0,10,"FIELD FLOW v2.1");

    sprintf(line,"Slave : %d",systemStatus.slaveId);
    oled.drawStr(0,24,line);

    oled.drawStr(0,36,
        systemStatus.ethernetLink ?
        "ETH : CONNECTED" :
        "ETH : DISCONNECTED");

    oled.drawStr(0,48,
        systemStatus.tcpConnected ?
        "TCP : CONNECTED" :
        "TCP : WAITING");

    sprintf(line,"Heap : %lu KB",
            systemStatus.freeHeap/1024);

    oled.drawStr(0,60,line);
}

void fieldflowDisplayLoop()
{
    if(millis()-lastRefresh < 200)
        return;

    lastRefresh = millis();

    oled.clearBuffer();
    renderHome();
    oled.sendBuffer();
}