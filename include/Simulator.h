#ifndef SIMULATOR_HH
#define SIMULATOR_HH

#include <cstdint>
#include "AXIMemory.h"


struct InstStatistic {
    uint32_t aluInsts = 0;
    uint32_t branchInsts = 0;
    uint32_t loadInsts = 0;
    uint32_t storeInsts = 0;
    uint32_t mulInsts = 0;
    uint32_t divInsts = 0;
};

class Simulator {
    private:
    uint32_t pc = 0x80000000;
    uint32_t rf[32] = {0};
    AXIMemory* memory = nullptr;
    uint32_t bits(uint32_t value, uint32_t hi, uint32_t lo){
        return (value >> lo) & ~((-1) << (hi - lo + 1));
    }
    uint32_t signExtend(uint32_t value, uint32_t width){
        if (bits(value, width - 1, width - 1) == 1) {
            return value | ((-1) << width);
        } else {
            return value & ~((-1) << width);
        }
    }
    uint32_t zeroExtend(uint32_t value, uint32_t width){
        return value & ~((-1) << width);
    }
    void executeRType(uint32_t inst);
    void executeIType(uint32_t inst);
    void executeBType(uint32_t inst);
    void executeSType(uint32_t inst);
    void executeJType(uint32_t inst);
    void executeUType(uint32_t inst);
    void executeStreamType(uint32_t inst);

    // instruction type
    InstStatistic instStat;

    public:
    Simulator(AXIMemory* memory): memory(memory) {}

    void step(uint32_t num);
    uint32_t getPC(){
        return pc;
    }
    uint32_t getRf(uint8_t rd){
        return rf[rd];
    }
    InstStatistic getInstStat(){
        return instStat;
    }
    std::string disassemble(uint32_t inst) {
        uint8_t opcode  = inst & 0x7f;
        uint8_t rd      = (inst >> 7) & 0x1f;
        uint8_t funct3  = (inst >> 12) & 0x7;
        uint8_t rs1     = (inst >> 15) & 0x1f;
        uint8_t rs2     = (inst >> 20) & 0x1f;
        uint8_t funct7  = (inst >> 25) & 0x7f;
    
        char buf[64];
    
        switch(opcode){
            case 0x33: { // R-type
                switch(funct7){
                    case 0x00: switch(funct3){
                        case 0x0: sprintf(buf,"add a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x1: sprintf(buf,"sll a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x2: sprintf(buf,"slt a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x3: sprintf(buf,"sltu a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x4: sprintf(buf,"xor a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x5: sprintf(buf,"srl a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x6: sprintf(buf,"or a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x7: sprintf(buf,"and a%d, a%d, a%d", rd, rs1, rs2); break;
                        default: sprintf(buf,"unknown"); break;
                    } break;
                    case 0x20: switch(funct3){
                        case 0x0: sprintf(buf,"sub a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x5: sprintf(buf,"sra a%d, a%d, a%d", rd, rs1, rs2); break;
                        default: sprintf(buf,"unknown"); break;
                    } break;
                    case 0x01: switch(funct3){ // MUL/DIV
                        case 0x0: sprintf(buf,"mul a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x1: sprintf(buf,"mulh a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x2: sprintf(buf,"mulhsu a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x3: sprintf(buf,"mulhu a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x4: sprintf(buf,"div a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x5: sprintf(buf,"divu a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x6: sprintf(buf,"rem a%d, a%d, a%d", rd, rs1, rs2); break;
                        case 0x7: sprintf(buf,"remu a%d, a%d, a%d", rd, rs1, rs2); break;
                        default: sprintf(buf,"unknown"); break;
                    } break;
                    default: sprintf(buf,"unknown"); break;
                }
            } break;
    
            case 0x13: { // I-type ALU
                uint32_t imm = signExtend(inst >> 20, 12);
                switch(funct3){
                    case 0x0: sprintf(buf,"addi a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x2: sprintf(buf,"slti a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x3: sprintf(buf,"sltiu a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x4: sprintf(buf,"xori a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x6: sprintf(buf,"ori a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x7: sprintf(buf,"andi a%d, a%d, %d", rd, rs1, imm); break;
                    case 0x1: sprintf(buf,"slli a%d, a%d, %d", rd, rs1, imm & 0x1F); break;
                    case 0x5: sprintf(buf,(inst & 0x40000000)?"srai a%d, a%d, %d":"srli a%d, a%d, %d", rd, rs1, imm & 0x1F); break;
                    default: sprintf(buf,"unknown"); break;
                }
            } break;
    
            case 0x03: { // load
                uint32_t imm = signExtend(inst >> 20, 12);
                switch(funct3){
                    case 0x0: sprintf(buf,"lb a%d, %d(a%d)", rd, imm, rs1); break;
                    case 0x1: sprintf(buf,"lh a%d, %d(a%d)", rd, imm, rs1); break;
                    case 0x2: sprintf(buf,"lw a%d, %d(a%d)", rd, imm, rs1); break;
                    case 0x4: sprintf(buf,"lbu a%d, %d(a%d)", rd, imm, rs1); break;
                    case 0x5: sprintf(buf,"lhu a%d, %d(a%d)", rd, imm, rs1); break;
                    default: sprintf(buf,"unknown"); break;
                }
            } break;
    
            case 0x23: { // store
                uint32_t imm = signExtend(((inst >> 25)<<5)|(bits(inst,11,7)),12);
                switch(funct3){
                    case 0x0: sprintf(buf,"sb a%d, %d(a%d)", rs2, imm, rs1); break;
                    case 0x1: sprintf(buf,"sh a%d, %d(a%d)", rs2, imm, rs1); break;
                    case 0x2: sprintf(buf,"sw a%d, %d(a%d)", rs2, imm, rs1); break;
                    default: sprintf(buf,"unknown"); break;
                }
            } break;
    
            case 0x63: { // branch
                uint32_t imm = signExtend((bits(inst,31,31)<<12)|(bits(inst,7,7)<<11)|(bits(inst,30,25)<<5)|(bits(inst,11,8)<<1),13);
                switch(funct3){
                    case 0x0: sprintf(buf,"beq a%d, a%d, %d", rs1, rs2, imm); break;
                    case 0x1: sprintf(buf,"bne a%d, a%d, %d", rs1, rs2, imm); break;
                    case 0x4: sprintf(buf,"blt a%d, a%d, %d", rs1, rs2, imm); break;
                    case 0x5: sprintf(buf,"bge a%d, a%d, %d", rs1, rs2, imm); break;
                    case 0x6: sprintf(buf,"bltu a%d, a%d, %d", rs1, rs2, imm); break;
                    case 0x7: sprintf(buf,"bgeu a%d, a%d, %d", rs1, rs2, imm); break;
                    default: sprintf(buf,"unknown"); break;
                }
            } break;
    
            case 0x37: sprintf(buf,"lui a%d, %d", rd, inst & 0xFFFFF000); break;
            case 0x17: sprintf(buf,"auipc a%d, %d", rd, inst & 0xFFFFF000); break;
            case 0x6F: sprintf(buf,"jal a%d, %d", rd, signExtend((bits(inst,31,31)<<20)|(bits(inst,21,30)<<1)|(bits(inst,20,20)<<11)|(bits(inst,12,19)<<12),21)); break;
            case 0x67: sprintf(buf,"jalr a%d, a%d, %d", rd, rs1, signExtend(inst>>20,12)); break;
    
            case 0x0B: { // stream type
                switch(funct3){
                    case 0x0: sprintf(buf,"cfg_i"); break;
                    case 0x1: sprintf(buf,"cfg_store"); break;
                    case 0x2: sprintf(buf,"cal_stream"); break;
                    case 0x3: sprintf(buf,"step_i"); break;
                    case 0x5: sprintf(buf,"cfg_load"); break;
                    default: sprintf(buf,"unknown stream"); break;
                }
            } break;
    
            default: sprintf(buf,"unknown"); break;
        }
        return std::string(buf);
    }
    
};

#endif