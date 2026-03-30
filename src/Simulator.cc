#include "Simulator.h"
#include "cfft.h"

void Simulator::step(uint32_t num) {
    uint32_t inst = memory->refMemoryRead(pc);
    uint8_t opcode = bits(inst, 6, 0);
    // std::cout << std::hex <<  <<  std::dec << std::endl;
    switch(opcode){
        case 0x0b: executeStreamType(inst); break;
        case 0x37: executeUType(inst); break;
        case 0x17: executeUType(inst); break;
        case 0x6F: executeJType(inst); break;
        case 0x67: executeIType(inst); break;
        case 0x63: executeBType(inst); break;
        case 0x03: executeIType(inst); break;
        case 0x23: executeSType(inst); break;
        case 0x13: executeIType(inst); break;
        case 0x33: executeRType(inst); break;
        default: break;
    }
    rf[0] = 0;
    if(opcode != 0x0b){
        cktS = false;
    }
}

void Simulator::executeRType(uint32_t inst) {
    uint8_t opcode  = bits(inst, 6, 0);
    uint8_t rd      = bits(inst, 11, 7);
    uint8_t rs1     = bits(inst, 19, 15);
    uint8_t rs2     = bits(inst, 24, 20);
    uint8_t funct7  = bits(inst, 31, 25);
    uint8_t funct3  = bits(inst, 14, 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    switch (opcode) {
        case 0x33: {
            switch (funct7) {
                case 0x0: {
                    instStat.aluInsts++;
                    switch (funct3) {
                        case 0x0: rf[rd] = value1 + value2; break;
                        case 0x1: rf[rd] = value1 << value2; break;
                        case 0x2: rf[rd] = (int32_t)value1 < (int32_t)value2; break;
                        case 0x3: rf[rd] = value1 < value2; break;
                        case 0x4: rf[rd] = value1 ^ value2; break;
                        case 0x5: rf[rd] = value1 >> value2; break;
                        case 0x6: rf[rd] = value1 | value2; break;
                        case 0x7: rf[rd] = value1 & value2; break;
                        default: break;
                    }
                    break;
                }
                case 0x20: {
                    instStat.aluInsts++;
                    switch (funct3) {
                        case 0x0: rf[rd] = value1 - value2; break;
                        case 0x5: rf[rd] = (int32_t)value1 >> value2; break;
                        default: break;
                    }
                    break;
                }
                case 0x01: {
                    switch (funct3) {
                        case 0x0: instStat.mulInsts++; rf[rd] = value1 * value2; break;
                        case 0x1: instStat.mulInsts++; rf[rd] = ((int64_t)(int32_t)value1 * (int64_t)(int32_t)value2) >> 32; break;
                        case 0x2: instStat.mulInsts++; rf[rd] = ((int64_t)(int32_t)value1 * (uint64_t)value2) >> 32; break;
                        case 0x3: instStat.mulInsts++; rf[rd] = ((uint64_t)value1 * (uint64_t)value2) >> 32; break;
                        case 0x4: instStat.divInsts++; rf[rd] = value2 == 0 ? -1 : (int32_t)value1 / (int32_t)value2; break;
                        case 0x5: instStat.divInsts++; rf[rd] = value2 == 0 ? -1 : value1 / value2; break;
                        case 0x6: instStat.divInsts++; rf[rd] = value2 == 0 ? value1 : (int32_t)value1 % (int32_t)value2; break;
                        case 0x7: instStat.divInsts++; rf[rd] = value2 == 0 ? value1 : value1 % value2; break;
                        default: break;
                    }
                }
                default: break;
            }
            break;
        }
        default: break;
    }
    pc += 4;
}

void Simulator::executeIType(uint32_t inst) {
    uint8_t opcode = bits(inst, 6, 0);
    uint8_t rd = bits(inst, 11, 7);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t imm = signExtend(bits(inst, 31, 20), 12);
    uint32_t value1 = rf[rs1];
    switch(opcode){
        case 0x13: {
            instStat.aluInsts++;
            switch(funct3){
                case 0x0: rf[rd] = value1 + imm; break;
                case 0x1: rf[rd] = value1 << (imm & 0x1F); break;
                case 0x2: rf[rd] = (int32_t)value1 < (int32_t)imm; break;
                case 0x3: rf[rd] = value1 < imm; break;
                case 0x4: rf[rd] = value1 ^ imm; break;
                case 0x5: rf[rd] = inst & 0x40000000 ? (int32_t)value1 >> (imm & 0x1F) : value1 >> (imm & 0x1F); break;
                case 0x6: rf[rd] = value1 | imm; break;
                case 0x7: rf[rd] = value1 & imm; break;
                default: break;
            }
            pc += 4;
            break;
        }
        case 0x03: {
            instStat.loadInsts++;
            switch(funct3){
                case 0x0: rf[rd] = signExtend(memory->refMemoryRead(value1 + imm), 8); break;
                case 0x1: rf[rd] = signExtend(memory->refMemoryRead(value1 + imm), 16); break;
                case 0x2: rf[rd] = memory->refMemoryRead(value1 + imm); break;
                case 0x4: rf[rd] = zeroExtend(memory->refMemoryRead(value1 + imm), 8); break;
                case 0x5: rf[rd] = zeroExtend(memory->refMemoryRead(value1 + imm), 16); break;
                default: break;
            }
            pc += 4;
            break;
        }
        case 0x67: {
            instStat.branchInsts++;
            rf[rd] = pc + 4;
            pc = value1 + imm;
            break;
        }
        default: break;
    }
}

void Simulator::executeBType(uint32_t inst) {
    uint8_t opcode = bits(inst, 6, 0);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t rs2 = bits(inst, 24, 20);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t imm = signExtend(bits(inst, 31, 31) << 12 | (bits(inst, 7, 7) << 11) | (bits(inst, 30, 25) << 5) | (bits(inst, 11, 8) << 1), 13);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    switch(opcode){
        case 0x63: {
            instStat.branchInsts++;
            switch(funct3){
                case 0x0: value1 == value2 ? pc += imm : pc += 4; break;
                case 0x1: value1 != value2 ? pc += imm : pc += 4; break;
                case 0x4: (int32_t)value1 < (int32_t)value2 ? pc += imm : pc += 4; break;
                case 0x5: (int32_t)value1 >= (int32_t)value2 ? pc += imm : pc += 4; break;
                case 0x6: value1 < value2 ? pc += imm : pc += 4; break;
                case 0x7: value1 >= value2 ? pc += imm : pc += 4; break;
                default: break;
            }
        }
        default: break;
    }
}

void Simulator::executeSType(uint32_t inst) {
    uint8_t opcode = bits(inst, 6, 0);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t rs2 = bits(inst, 24, 20);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t imm = signExtend(bits(inst, 31, 25) << 5 | bits(inst, 11, 7), 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    switch(opcode){
        case 0x23: {
            instStat.storeInsts++;
            switch(funct3){
                case 0x0: memory->refMemoryWrite(value1 + imm, value2, 0x1); break;
                case 0x1: memory->refMemoryWrite(value1 + imm, value2, 0x3); break;
                case 0x2: memory->refMemoryWrite(value1 + imm, value2, 0xf); break;
                default: break;
            }
        }
        default: break;
    }
    pc += 4;
}

void Simulator::executeUType(uint32_t inst) {

    uint8_t opcode = bits(inst, 6, 0);
    uint8_t rd = bits(inst, 11, 7);
    uint32_t imm = bits(inst, 31, 12) << 12;
    switch(opcode){
        case 0x37: instStat.aluInsts++; rf[rd] = imm; break;
        case 0x17: instStat.aluInsts++; rf[rd] = pc + imm; break;
        default: break;
    }
    pc += 4;
}

void Simulator::executeJType(uint32_t inst) {
    uint8_t opcode = bits(inst, 6, 0);
    uint8_t rd = bits(inst, 11, 7);
    uint32_t imm = signExtend(bits(inst, 31, 31) << 20 | (bits(inst, 19, 12) << 12) | (bits(inst, 20, 20) << 11) | (bits(inst, 30, 21) << 1), 21);
    switch(opcode){
        case 0x6F: {
            instStat.branchInsts++;
            rf[rd] = pc + 4;
            pc += imm;
            break;
        }
        default: break;
    }
}

//FFT
#define N2 32   // 外层长度
#define N1 128   // 内层长度
#define FFT_N 4096
#define FFT_32 32
int initTemp = 0;
static complex_t twiddle_stage_32[FFT_32/2];
static complex_t temp[N1][N2];
void init_temp() {
    if(initTemp) return;
    for (int i = 0; i < FFT_N; i++) {
        temp[i/32][i%32].real = i;
        temp[i/32][i%32].imag = i;
    }
    for (int i = 16; i < 32; i++) {
        temp[0][i].real = 0;
        temp[0][i].imag = 0;
    }    
    initTemp = 1;
}  


static inline void complex_add(complex_t a, complex_t b, complex_t* result) {
    result->real = a.real + b.real;
    result->imag = a.imag + b.imag;
}

static inline void complex_subtract(complex_t a, complex_t b, complex_t* result) {
    result->real = a.real - b.real;
    result->imag = a.imag - b.imag;
}

static inline void complex_multiply(complex_t a, complex_t b, complex_t* result) {
    // Use 64-bit intermediate to avoid overflow, then scale back
    int64_t real_temp = ((int64_t)a.real * b.real - (int64_t)a.imag * b.imag);
    int64_t imag_temp = ((int64_t)a.real * b.imag + (int64_t)a.imag * b.real);
    
    // Scale back from Q30 to Q15
    result->real = (int32_t)(real_temp >> FIXED_POINT_BITS);
    result->imag = (int32_t)(imag_temp >> FIXED_POINT_BITS);
}

int block = 0;
int stage = 0;
int p = 0;
int q = 0;
int cnt = 0;

int m = 16;  
int s = 1;

int ifCal = 0;
int total = 0;
int curE = 0;
int curO = 0;

int tag = 0;
complex_t add_res,sub_res,orRes;
complex_t y[FFT_32];
complex_t *dst = y;
complex_t *src = temp[block];

void Simulator::executeStreamType(uint32_t inst) {
    uint8_t opcode  = bits(inst, 6, 0);
    uint8_t rd      = bits(inst, 11, 7);
    uint8_t rs1     = bits(inst, 19, 15);
    uint8_t rs2     = bits(inst, 24, 20);
    uint8_t funct7  = bits(inst, 31, 25);
    uint8_t funct3  = bits(inst, 14, 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    pc += 4;

    cktS = false;
    if (funct3 == 0x02 || funct3 == 0x06 || funct3 == 0x07){
        if(!ifCal){
            init_temp();
            int tw_idx = (p << stage) ;
            complex_t wp = twiddle_stage_32[tw_idx];
            complex_t a = src[q + s * (p + 0)];
            complex_t b = src[q + s * (p + m)];
            complex_add(a, b, &add_res);
            complex_subtract(a,b,&sub_res);
            complex_multiply(sub_res, wp, &orRes);
            
            dst[q + s*(2*p+0)] = add_res;
            dst[q + s*(2*p+1)] = orRes;

            printf("==========================================================\n");
            curE = stage*32 + q + s*(2*p+0);
            curO = stage*32 + q + s*(2*p+1);
            printf("block%d, stage%d, iter%d, odd%d, even%d\n", block, stage, total%16,q + s * (p + 0), q + s * (p + m));
            total++;
            q += 1;
            if(q >= s){
                p += 1;
                q = 0;
                if(p >= m){
                    stage += 1;
                    p = 0;
                    m >>= 1;
                    s <<= 1;
                    // for (int ii=0;ii<32;ii++){
                    //     printf(" \n")
                    // }
                    complex_t *tmp = src;
                    src = dst;
                    dst = tmp;
                    if(stage >= 5){
                        stage = 0;
                        m = 16;
                        s = 1;
                        block++;
                        src = temp[block];
                    }
                }
            }
            ifCal = 1;
        }

        int res = 0;
        switch (funct3){
            case 0x02: {
                assert(cnt == 0 || cnt == 1);
                res = cnt==0 ? add_res.real : add_res.imag;
                printf("add! res is %d\n", res);
                curSWidx = curE*2 + cnt;
                cnt++;
                cktS = true;
                if(tag==2){
                    tag = 0;
                }
                break;
            }
            case 0x07: {
                if(funct7 == 0x08){
                    assert(cnt == 2 || cnt == 3);
                    rf[rd] = cnt==2 ? sub_res.real : sub_res.imag;
                    printf("sub! res is %d\n", rf[rd]);
                    cnt++;
                    if(cnt == 4 && tag == 2){
                        cnt = 0;//back to cal_stream_rd_add
                        ifCal = 0;
                    }
                    break;
                }
                else{
                    assert(funct7 == 0x00);
                    assert(cnt == 0 || cnt == 1);
                    rf[rd] = cnt==0 ? add_res.real : add_res.imag;
                    printf("add_rd! res is %d\n", rf[rd]);
                    cnt++;
                    break;
                }
            }
            case 0x06: {
                assert(cnt == 4 || cnt == 5);
                if (stage == 4 ){
                    tag++;
                    assert(tag <= 2); //因为stage提前++，所以执行完最后两条指令
                }
                res = cnt==4 ? orRes.real : orRes.imag;
                //printf("value1 is %d,value2 is %d,or res is %d\n",value1,value2,value1 | value2);
                printf("OR! res is %d\n", res);
                curSWidx = curO*2 + (cnt-4);
                cnt = cnt== 4 ? 5 : 0;
                if(cnt == 0) { ifCal = 0; }
                cktS = true;
                break;
            }
            default: break;
        }
        curSWdata = res;
    }
}

