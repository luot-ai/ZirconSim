#ifndef EMULATOR_HH
#define EMULATOR_HH

#include <cstdint>
#include "AXIMemory.h"
#include "Statistic.h"
#include "Simulator.h"

#define NCOMMIT 2

class Emulator {
    private:
    VCPU* cpu = nullptr;
    AXIMemory* memory = nullptr;
    Statistic* stat = nullptr;
    Simulator* simulator = nullptr;


    uint32_t baseAddr = 0x80000000;
    uint32_t deadInstruction = 0x80000000;
    uint32_t stallThreshold = 1000;

    uint8_t rnmTable[32] = {0};
    uint32_t stallCount = 0;
    
    VerilatedVcdC *m_trace = nullptr;
    uint64_t simTime = 0;

    inline uint32_t bits(uint32_t value, uint32_t hi, uint32_t lo) {
        return (value >> lo) & ~((-1) << (hi - lo + 1));
    }
    inline void rnmTableUpdate(uint8_t rd, uint8_t prd) {
        rnmTable[rd] = prd;
    }

    // difftest
    bool difftestPC(uint32_t pc);
    bool difftestRF(uint8_t rd, uint32_t rdData, uint32_t pc);
    bool difftestStep(uint8_t rd, uint32_t rdData, uint32_t pc, uint32_t step);

    public:
    Emulator(
        VCPU* cpu, 
        AXIMemory* memory, 
        Statistic* stat, 
        Simulator* simulator,
        VerilatedVcdC *m_trace
    ): cpu(cpu), memory(memory), stat(stat), simulator(simulator), m_trace(m_trace) {}

    
    inline bool simEnd(uint32_t instruction) {
        return instruction == deadInstruction;
    }
    inline bool stallForTooLong() {
        return stallCount > stallThreshold;
    }
    void reset();
    int step(uint32_t num);

};

#endif