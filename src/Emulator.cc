#include "Emulator.h"
#include <iostream>
#include <filesystem>
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

uint32_t bits(uint32_t value, uint32_t hi, uint32_t lo){
    return (value >> lo) & ~((-1) << (hi - lo + 1));
}


int Emulator::step(uint32_t num, std::string imgName) {
    std::string reportsDir = "profiling/" + imgName;
    if(!std::filesystem::exists(reportsDir)){
        std::filesystem::create_directories(reportsDir);
    }
    std::ofstream baselog = std::ofstream(reportsDir + "/base.log");
    std::ofstream timelinelog = std::ofstream(reportsDir + "/timeline.log");
    if (!baselog.is_open()) {
        std::cerr << "failed to open base.log\n";
        return -4;
    }
    if (!timelinelog.is_open()) {
        std::cerr << "failed to open timeline.log\n";
        return -4;
    }

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
    uint32_t lastCmtCycles = 0;
    uint32_t seq = 0;

    uint64_t *fetchCycles[2]     = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_fetch,     &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_fetch};
    uint64_t *preDecodeCycles[2] = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_preDecode, &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_preDecode};
    uint64_t *decodeCycles[2]    = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_decode,    &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_decode};
    uint64_t *dispatchCycles[2]  = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_dispatch,  &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_dispatch};
    uint64_t *issueCycles[2]     = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_issue,     &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_issue};
    uint64_t *readOpCycles[2]    = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_readOp,    &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_readOp};
    uint64_t *exeCycles[2]       = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_exe,       &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_exe};
    uint64_t *exe1Cycles[2]      = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_exe1,      &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_exe1};
    uint64_t *exe2Cycles[2]      = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_exe2,      &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_exe2};
    uint64_t *wbCycles[2]        = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_wb,        &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_wb};
    uint64_t *wbROBCycles[2]     = {&cpu->io_dbg_cmt_robDeq_deq_0_bits_cycle_wbROB,     &cpu->io_dbg_cmt_robDeq_deq_1_bits_cycle_wbROB};
    uint64_t **allCycles[] = {
        fetchCycles, preDecodeCycles, decodeCycles, dispatchCycles, issueCycles,
        readOpCycles, exeCycles, exe1Cycles, exe2Cycles, wbCycles, wbROBCycles
    };
    const char *stageNames[] = {
        "fetch", "preDecode", "decode", "dispatch", "issue",
        "readOp", "exe", "exe1", "exe2", "wb", "wbROB"
    };
    const int numStages = sizeof(allCycles) / sizeof(allCycles[0]);

    while(num-- > 0){
        stat->addCycles(1);
        if (cpu->io_dbg_axi_rdDoneVec != 0) {
            timelinelog << "end" << ","
                    << +cpu->io_dbg_axi_rdDoneVec << ","
                    << +cpu->io_dbg_axi_Cycles << ","
                    << stat->getCycles() << std::endl;
        }
        if (cpu->io_dbg_axi_rdVldVec != 0) {
            timelinelog << "start" << ","
                    << +cpu->io_dbg_axi_rdVldVec << ","
                    << stat->getCycles() << std::endl;
        }

        for(int i = 0; i < NCOMMIT; i++){
            if(stallForTooLong()){
                return -3;
            }
            if(*cmtVlds[i]){
                stallCount = 0;
                stat->addInsts(1);
                stat->pcBufferPush(*cmtPCs[i]);
                uint32_t cmtInst = memory->debugRead(*cmtPCs[i]);

                std::string asmStr = simulator->disassemble(cmtInst);
                uint8_t opcode  = bits(cmtInst, 6, 0);
                bool isBranch = opcode == 0x6F || opcode == 0x63 || opcode == 0x67;
                // 输出一条指令的记录
                baselog << seq << ","
                        << "0x" << std::hex << *cmtPCs[i] << std::dec << ","
                        << "\"" << asmStr << "\","
                        << lastCmtCycles;
                for (int s = 0; s < numStages; s++) {
                    baselog << "," << (*allCycles[s][i] + 1);
                }
                baselog << "," << stat->getCycles()
                        << "," << isBranch
                        << std::endl;       
                seq++;

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
        if(*cmtVlds[0]){
            lastCmtCycles = stat->getCycles();
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
    baselog << "]" << std::endl;
    return 1;
}

