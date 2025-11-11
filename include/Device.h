#ifndef DEVICE_HH
#define DEVICE_HH

#include <cstdint>
#include <iostream>

class Device {
    private:
    uint32_t baseAddr = 0xa0000000;
    uint32_t uartAddr = baseAddr + 0x00003f8;

    public:
    uint32_t read(uint32_t addr);
    void uart_write(uint8_t data) {
        std::cout << (char)data;
        std::cout << std::flush;
    }
    void write(uint32_t addr, uint32_t data) {
        if (addr == uartAddr) {
            uart_write(data);
        }
    }

};

#endif