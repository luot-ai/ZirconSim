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

std::string disassemble(uint32_t inst) {
    uint8_t opcode  = bits(inst, 6, 0);
    uint8_t rd      = bits(inst, 11, 7);
    uint8_t rs1     = bits(inst, 19, 15);
    uint8_t rs2     = bits(inst, 24, 20);
    uint8_t funct7  = bits(inst, 31, 25);
    uint8_t funct3  = bits(inst, 14, 12);

    char buf[64];
    switch (opcode)
    {
    case 0x0b:
        switch (funct3)
        {
        case 0x0:
            sprintf(buf, "cfg_i");
            break;
        case 0x1:
            sprintf(buf, "cfg_store");
            break;
        case 0x2:
            sprintf(buf, "cal_stream",
                    rs2, (rs1 & 0x3), (rs1 >> 2) & 0x3);
            break;
        case 0x3:
            sprintf(buf, "step_i");
            break;
        case 0x5:
            sprintf(buf, "cfg_load");
            break;
        default:
            sprintf(buf, "unknown stream");
            break;
        }
        break;
    case 0x33: // R-type
        if (funct3 == 0 && funct7 == 0x00)
            sprintf(buf, "add a%d, a%d, a%d", rd, rs1, rs2);
        else if (funct3 == 0 && funct7 == 0x20)
            sprintf(buf, "sub a%d, a%d, a%d", rd, rs1, rs2);
        else if (funct3 == 0x7)
            sprintf(buf, "and a%d, a%d, a%d", rd, rs1, rs2);
        else
            sprintf(buf, "unknown");
        break;
    case 0x13: // I-type (addi)
        sprintf(buf, "addi a%d, a%d, %d", rd, rs1, (int32_t)(inst) >> 20);
        break;
    case 0x03: // load
        if (funct3 == 0x2)
            sprintf(buf, "lw a%d, %d(a%d)", rd, (int32_t)(inst) >> 20, rs1);
        else
            sprintf(buf, "unknown");
        break;
    case 0x23: // store
        if (funct3 == 0x2)
        {
            int imm = ((inst >> 7) & 0x1f) | ((inst >> 25) << 5);
            sprintf(buf, "sw a%d, %d(a%d)", rs2, imm, rs1);
        }
        else
            sprintf(buf, "unknown");
        break;
    case 0x63: // branch
        if (funct3 == 0x0)
        {
            int imm = ((inst >> 7 & 0x1) << 11) |
                      ((inst >> 8 & 0xf) << 1) |
                      ((inst >> 25 & 0x3f) << 5) |
                      ((inst >> 31) << 12);
            sprintf(buf, "beq a%d, a%d, %d", rs1, rs2, imm);
        }
        else
            sprintf(buf, "unknown");
        break;
    default:
        sprintf(buf, "unknown");
    }
    return std::string(buf);
}


int Emulator::step(uint32_t num, std::string imgName) {
    std::string reportsDir = "profiling/" + imgName;
    if(!std::filesystem::exists(reportsDir)){
        std::filesystem::create_directories(reportsDir);
    }
    std::ofstream baselog = std::ofstream(reportsDir + "/base.log");
    if (!baselog.is_open()) {
        std::cerr << "failed to open base.log\n";
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

                std::string asmStr = disassemble(cmtInst);
                uint8_t opcode  = bits(cmtInst, 6, 0);
                bool isBranch = opcode == 0x6F || opcode == 0x63 || opcode == 0x67;
                baselog << seq << ","
                << "0x" << std::hex << *cmtPCs[i] << std::dec << ","
                << "\"" << asmStr << "\"" << ","
                << lastCmtCycles << ","
                << (stat->getCycles() - lastCmtCycles) << ","
                << isBranch 
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

