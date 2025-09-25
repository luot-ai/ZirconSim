#include "Emulator.h"
#include <iostream>
#include <thread>
#include <chrono>
#include "utils.h"

// #define DUMP_WAVE 0

void Emulator::reset() {
    cpu->reset = 1;
    cpu->clock = 0;
    cpu->eval();
    cpu->clock = 1;
    cpu->eval();
    cpu->reset = 0;
}

bool Emulator::difftestPC(uint32_t pc) {
    return simulator->getPC() == pc;
}
bool Emulator::difftestRF(uint8_t rd, uint32_t rdData, uint32_t pc) {
    return simulator->getRf(rd) == rdData;
}
bool Emulator::difftestStep(uint8_t rd, uint32_t rdData, uint32_t pc, uint32_t step) {
    if(!difftestPC(pc)){
        std::cout << ANSI_FG_RED << "PC mismatch at pc " << std::hex << simulator->getPC() << ", dut: " << pc << ANSI_NONE << std::endl;
        return false;
    }
    for(int i = 0; i < step; i++){
        simulator->step(1);
    }
    if(!difftestRF(rd, rdData, pc)){
        std::cout << ANSI_FG_RED << "RF mismatch at pc " << std::hex << pc << std::dec;
        std::cout << ", reg " << (uint32_t)rd << "(preg: " << (uint32_t)(rnmTable[rd]) << "), dut: " << std::hex << rdData;
        std::cout << ", ref: " << simulator->getRf(rd) << std::dec << ANSI_NONE << std::endl;
        return false;
    }
    return true;
}
int Emulator::step(uint32_t num) {

    std::thread printThread([this](){
        while(true){
            std::this_thread::sleep_for(std::chrono::seconds(1));
            std::cout << "\r";
            std::cout << "Total cycles: " << stat->getCycles() << ", IPC: " << stat->getIPC();
            std::cout << std::flush;
        }
    });
    printThread.detach();
    
    uint8_t *cmtVlds[2] = {&cpu->io_dbg_cmt_robDeq_deq_0_valid, &cpu->io_dbg_cmt_robDeq_deq_1_valid};
    uint32_t *cmtPCs[2] = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_pc, &cpu->io_dbg_cmt_robDeq_deq_1_bits_pc};
    uint8_t *cmtPrds[2] = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_prd, &cpu->io_dbg_cmt_robDeq_deq_1_bits_prd};
    uint32_t *dbgRf = &cpu->io_dbg_rf_rf_0;
    while(num-- > 0){
        stat->addCycles(1);
        for(int i = 0; i < NCOMMIT; i++){
            if(stallForTooLong()){
                return -3;
            }
            if(*cmtVlds[i]){
                stallCount = 0;
                stat->addInsts(1);
                stat->pcBufferPush(*cmtPCs[i]);
                uint32_t cmtInst = memory->debugRead(*cmtPCs[i]);
                uint8_t cmtRd = bits(cmtInst, 11, 7);
                if(simEnd(cmtInst)){
                    return (dbgRf[rnmTable[10]] == 0 ? 0 : -1);
                }
                if(*cmtPrds[i] != 0){
                    rnmTableUpdate(cmtRd, *cmtPrds[i]);
                }
                if(!difftestStep(cmtRd, dbgRf[rnmTable[cmtRd]], *cmtPCs[i], 1)){
                    return -2;
                }
            }
            

        }
        memory->write(cpu);
        memory->read(cpu);

        stallCount++;
        cpu->clock = 0;
        cpu->eval();
        cpu->clock = 1;
        cpu->eval();
#ifdef DUMP_WAVE
        m_trace->dump(simTime);
        simTime++;
#endif
    }
    return 1;
}

