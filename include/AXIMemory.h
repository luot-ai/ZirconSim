#ifndef AXIMEMORY_HH
#define AXIMEMORY_HH

#include <verilated_vcd_c.h>
#include "VCPU.h"
#include <cstdint>
#include <unordered_map>
#include <fstream>
#include "Device.h"


enum class AXIReadState {
    IDLE, AR, R
};
enum class AXIWriteState {
    IDLE, AW, W, B
};

struct AXIReadConfig {
    uint32_t araddr;
    uint8_t arlen;
    uint8_t arsize;
    uint8_t arburst;
    AXIReadState state = AXIReadState::IDLE;
};
struct AXIWriteConfig {
    uint32_t awaddr;
    uint8_t awlen;
    uint8_t awsize;
    uint8_t awburst;
    uint8_t wstrb;
    AXIWriteState state = AXIWriteState::IDLE;
};


class AXIMemory {
    private:
    std::unordered_map<uint32_t, uint32_t> memory;
    std::unordered_map<uint32_t, uint32_t> refMemory;
    Device* device = nullptr;
    uint32_t byteMasks[4] = {0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000};
    uint32_t randSeqIndex = 0;
    uint8_t randSeq[1024] = {0};

    AXIReadConfig readConfig;
    AXIWriteConfig writeConfig;

    

    public:
    AXIMemory(std::string imgPath, uint32_t baseAddr, Device* device);
    uint8_t nextRand();
    void read(VCPU* cpu);
    void write(VCPU* cpu);
    uint32_t debugRead(uint32_t addr);
    uint32_t refMemoryRead(uint32_t addr);
    void refMemoryWrite(uint32_t addr, uint32_t data, uint8_t wstrb);

};

#endif