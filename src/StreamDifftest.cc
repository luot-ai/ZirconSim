#include "StreamDifftest.h"
#include "cfft.h"
#include <cassert>
#include <iostream>

namespace {

uint32_t bits(uint32_t value, uint32_t hi, uint32_t lo) {
    return (value >> lo) & ~((-1) << (hi - lo + 1));
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
    int64_t real_temp = ((int64_t)a.real * b.real - (int64_t)a.imag * b.imag);
    int64_t imag_temp = ((int64_t)a.real * b.imag + (int64_t)a.imag * b.real);
    result->real = (int32_t)(real_temp >> FIXED_POINT_BITS);
    result->imag = (int32_t)(imag_temp >> FIXED_POINT_BITS);
}

constexpr int N2 = 32;
constexpr int N1 = 128;
constexpr int FFT_N = 4096;
constexpr int FFT_32 = 32;

bool fftTempInitialized = false;
complex_t twiddleStage32[FFT_32 / 2];
complex_t fftTemp[N1][N2];
complex_t fftY[FFT_32];
complex_t fftAddRes;
complex_t fftSubRes;
complex_t fftOrRes;
complex_t* fftDst = fftY;
complex_t* fftSrc = fftTemp[0];

void init_fft_temp() {
    if (fftTempInitialized) {
        return;
    }
    for (int i = 0; i < FFT_N; i++) {
        fftTemp[i / 32][i % 32].real = i;
        fftTemp[i / 32][i % 32].imag = i;
    }
    for (int i = 16; i < 32; i++) {
        fftTemp[0][i].real = 0;
        fftTemp[0][i].imag = 0;
    }
    fftTempInitialized = true;
}

}

StreamDifftestMode StreamDifftest::modeFromString(const std::string& modeName) {
    if (modeName == "none" || modeName == "off" || modeName == "0") {
        return StreamDifftestMode::None;
    }
    if (modeName == "add" || modeName == "stream-add" || modeName == "stream_add") {
        return StreamDifftestMode::StreamAdd;
    }
    if (modeName == "gemm" || modeName == "matrix") {
        return StreamDifftestMode::Gemm;
    }
    if (modeName == "fir") {
        return StreamDifftestMode::Fir;
    }
    if (modeName == "fft" || modeName == "fft32" || modeName == "cfft") {
        return StreamDifftestMode::Fft32;
    }
    return StreamDifftestMode::None;
}

StreamDifftestMode StreamDifftest::inferModeFromImage(const std::string& imgName) {
    if (imgName.find("cfft") != std::string::npos || imgName.find("fft") != std::string::npos) {
        return StreamDifftestMode::Fft32;
    }
    if (imgName.find("stream-add") != std::string::npos || imgName.find("stream_add") != std::string::npos) {
        return StreamDifftestMode::StreamAdd;
    }
    if (imgName.find("matrix") != std::string::npos || imgName.find("gemm") != std::string::npos) {
        return StreamDifftestMode::Gemm;
    }
    if (imgName.find("FIR") != std::string::npos || imgName.find("fir") != std::string::npos) {
        return StreamDifftestMode::Fir;
    }
    return StreamDifftestMode::None;
}

const char* StreamDifftest::modeName(StreamDifftestMode mode) {
    switch (mode) {
        case StreamDifftestMode::StreamAdd: return "stream-add";
        case StreamDifftestMode::Gemm: return "gemm";
        case StreamDifftestMode::Fir: return "fir";
        case StreamDifftestMode::Fft32: return "fft32";
        case StreamDifftestMode::None:
        default: return "none";
    }
}

void StreamDifftest::setMode(StreamDifftestMode nextMode) {
    mode = nextMode;
    gemmI = 0;
    gemmJ = 0;
    gemmK = 0;
    for (auto& fifo : gemmFifos) {
        fifo = GemmFifoConfig{};
    }
    addIndex = 0;
    for (auto& fifo : addFifos) {
        fifo = GemmFifoConfig{};
    }
    firTap = 0;
    firWindow = 0;
    for (auto& fifo : firFifos) {
        fifo = GemmFifoConfig{};
    }
    resetFft32();
}

StreamDifftestResult StreamDifftest::execute(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    switch (mode) {
        case StreamDifftestMode::StreamAdd: return executeStreamAdd(inst, rf, memory);
        case StreamDifftestMode::Gemm: return executeGemm(inst, rf, memory);
        case StreamDifftestMode::Fir: return executeFir(inst, rf, memory);
        case StreamDifftestMode::Fft32: return executeFft32(inst, rf, memory);
        case StreamDifftestMode::None:
        default: return executeNone(inst, rf, memory);
    }
}

StreamDifftestResult StreamDifftest::executeNone(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    (void)inst;
    (void)rf;
    (void)memory;
    return {};
}

StreamDifftestResult StreamDifftest::executeStreamAdd(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    StreamDifftestResult result;
    uint8_t rd = bits(inst, 11, 7);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t rs2 = bits(inst, 24, 20);
    uint8_t funct7 = bits(inst, 31, 25);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    uint32_t fifoId = value2 & 0x3;

    switch (funct3) {
        case 0x0:
            if (funct7 == 0x00) {
                addFifos[fifoId].outer = value1 & 0xffff;
                addFifos[fifoId].length = value1 >> 16;
            } else if (funct7 == 0x01) {
                addFifos[fifoId].limit = value1;
            } else if (funct7 == 0x02) {
                addFifos[fifoId].repeat = value1;
            }
            break;
        case 0x1:
            addFifos[fifoId].base = value1;
            break;
        case 0x3:
            if (funct7 == 0x01) {
                addFifos[fifoId].tileStride = value1;
            } else {
                addFifos[fifoId].stride = value1;
            }
            break;
        case 0x4:
            addFifos[fifoId].reuse = value1;
            break;
        case 0x5:
            addFifos[fifoId].base = value1;
            break;
        case 0x6:
            if (rd == 0) {
                addFifos[fifoId].tileStride = value1;
            }
            break;
        case 0x2: { //TODO:这里默认是 SSS 
            uint32_t src0 = value1 & 0x3;
            uint32_t src1 = (value1 >> 2) & 0x3;
            uint32_t dst = value2 & 0x3;
            uint32_t stride0 = addFifos[src0].stride ? addFifos[src0].stride : 4;
            uint32_t stride1 = addFifos[src1].stride ? addFifos[src1].stride : 4;
            uint32_t aAddr = addFifos[src0].base + addIndex * stride0;
            uint32_t bAddr = addFifos[src1].base + addIndex * stride1;
            uint32_t a = memory->refMemoryRead(aAddr);
            uint32_t b = memory->refMemoryRead(bAddr);

            result.wValid = true;
            result.wData = a + b; //TODO:默认加法
            result.wIdx = addIndex;

            (void)dst;
            addIndex++;
            break;
        }
        default:
            break;
    }

    return result;
}

StreamDifftestResult StreamDifftest::executeGemm(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    StreamDifftestResult result;
    uint8_t rd = bits(inst, 11, 7);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t rs2 = bits(inst, 24, 20);
    uint8_t funct7 = bits(inst, 31, 25);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    uint32_t fifoId = value2 & 0x3;

    switch (funct3) {
        case 0x0:
            if (funct7 == 0x00) {
                gemmFifos[fifoId].outer = value1 & 0xffff;
                gemmFifos[fifoId].length = value1 >> 16;
            } else if (funct7 == 0x01) {
                gemmFifos[fifoId].limit = value1;
            } else if (funct7 == 0x02) {
                gemmFifos[fifoId].repeat = value1;
            }
            break;
        case 0x3:
            if (funct7 == 0x01) {
                gemmFifos[fifoId].tileStride = value1;
            } else {
                gemmFifos[fifoId].stride = value1;
            }
            break;
        case 0x4:
            gemmFifos[fifoId].reuse = value1;
            break;
        case 0x5:
            gemmFifos[fifoId].base = value1;
            break;
        case 0x6:
            if (rd == 0) {
                gemmFifos[fifoId].tileStride = value1;
            }
            break;
        case 0x7: { //TODO:这里默认是 SSR
            uint32_t kSize = gemmFifos[0].limit ? gemmFifos[0].limit : 32;
            uint32_t nSize = gemmFifos[0].repeat ? gemmFifos[0].repeat : 32;
            uint32_t aAddr = gemmFifos[0].base + (gemmI * kSize + gemmK) * 4;
            uint32_t bAddr = gemmFifos[1].base + (gemmK * nSize + gemmJ) * 4;
            int32_t a = (int32_t)memory->refMemoryRead(aAddr);
            int32_t b = (int32_t)memory->refMemoryRead(bAddr);

            result.rdValid = true;
            result.rd = rd;
            result.rdData = (uint32_t)(a * b); //TODO:默认乘法

            gemmK++;
            if (gemmK >= kSize) {
                gemmK = 0;
                gemmJ++;
                if (gemmJ >= nSize) {
                    gemmJ = 0;
                    gemmI++;
                }
            }
            break;
        }
        default:
            break;
    }

    return result;
}

StreamDifftestResult StreamDifftest::executeFir(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    StreamDifftestResult result;
    uint8_t rd = bits(inst, 11, 7);
    uint8_t rs1 = bits(inst, 19, 15);
    uint8_t rs2 = bits(inst, 24, 20);
    uint8_t funct7 = bits(inst, 31, 25);
    uint8_t funct3 = bits(inst, 14, 12);
    uint32_t value1 = rf[rs1];
    uint32_t value2 = rf[rs2];
    uint32_t fifoId = value2 & 0x3;

    switch (funct3) {
        case 0x0:
            if (funct7 == 0x00) {
                firFifos[fifoId].outer = value1 & 0xffff;
                firFifos[fifoId].length = value1 >> 16;
            } else if (funct7 == 0x01) {
                firFifos[fifoId].limit = value1;
            } else if (funct7 == 0x02) {
                firFifos[fifoId].repeat = value1;
            } else if (funct7 == 0x03) {
                firFifos[fifoId].offset = value1;
            }
            break;
        case 0x3:
            if (funct7 == 0x01) {
                firFifos[fifoId].tileStride = value1;
            } else {
                firFifos[fifoId].stride = value1;
            }
            break;
        case 0x4:
            if (funct7 == 0x00) {
                firFifos[fifoId].reuse = value1;
            }
            break;
        case 0x5:
            firFifos[fifoId].base = value1;
            break;
        case 0x7:
            if (funct7 == 0x10) {
                uint32_t src0 = value1 & 0x3;
                uint32_t src1 = (value1 >> 2) & 0x3;
                uint32_t filterOrder = firFifos[src0].limit ? firFifos[src0].limit : firFifos[src0].length;
                if (filterOrder == 0) {
                    filterOrder = 16;
                }
                uint32_t stride0 = firFifos[src0].stride ? firFifos[src0].stride : 4;
                uint32_t stride1 = firFifos[src1].stride ? firFifos[src1].stride : 4;
                uint32_t coeffIndex = firTap + firFifos[src0].offset;
                uint32_t inputIndex = firWindow + firTap;
                if (firFifos[src1].offset > 0) {
                    inputIndex += firFifos[src1].offset - 1;
                }
                uint32_t coeffAddr = firFifos[src0].base + coeffIndex * stride0;
                uint32_t inputAddr = firFifos[src1].base + inputIndex * stride1;
                int32_t coeff = (int32_t)memory->refMemoryRead(coeffAddr);
                int32_t input = (int32_t)memory->refMemoryRead(inputAddr);

                result.rdValid = true;
                result.rd = rd;
                result.rdData = (uint32_t)(coeff * input);

                firTap++;
                if (firTap >= filterOrder) {
                    firTap = 0;
                    firWindow++;
                }
            }
            break;
        default:
            break;
    }

    return result;
}

void StreamDifftest::resetFft32() {
    fftBlock = 0;
    fftStage = 0;
    fftP = 0;
    fftQ = 0;
    fftCnt = 0;
    fftM = 16;
    fftS = 1;
    fftIfCal = 0;
    fftTotal = 0;
    fftCurE = 0;
    fftCurO = 0;
    fftTag = 0;
    fftDst = fftY;
    fftSrc = fftTemp[0];
}

StreamDifftestResult StreamDifftest::executeFft32(uint32_t inst, uint32_t rf[32], AXIMemory* memory) {
    (void)memory;
    StreamDifftestResult result;
    uint8_t rd = bits(inst, 11, 7);
    uint8_t funct7 = bits(inst, 31, 25);
    uint8_t funct3 = bits(inst, 14, 12);

    if (funct3 != 0x02 && funct3 != 0x06 && funct3 != 0x07) {
        return result;
    }

    if (!fftIfCal) {
        init_fft_temp();
        int twIdx = (fftP << fftStage);
        complex_t wp = twiddleStage32[twIdx];
        complex_t a = fftSrc[fftQ + fftS * (fftP + 0)];
        complex_t b = fftSrc[fftQ + fftS * (fftP + fftM)];
        complex_add(a, b, &fftAddRes);
        complex_subtract(a, b, &fftSubRes);
        complex_multiply(fftSubRes, wp, &fftOrRes);

        fftDst[fftQ + fftS * (2 * fftP + 0)] = fftAddRes;
        fftDst[fftQ + fftS * (2 * fftP + 1)] = fftOrRes;

        std::cout << "==========================================================" << std::endl;
        fftCurE = fftStage * 32 + fftQ + fftS * (2 * fftP + 0);
        fftCurO = fftStage * 32 + fftQ + fftS * (2 * fftP + 1);
        std::cout << "block" << fftBlock << ", stage" << fftStage
                  << ", iter" << fftTotal % 16
                  << ", odd" << fftQ + fftS * (fftP + 0)
                  << ", even" << fftQ + fftS * (fftP + fftM) << std::endl;
        fftTotal++;
        fftQ += 1;
        if (fftQ >= fftS) {
            fftP += 1;
            fftQ = 0;
            if (fftP >= fftM) {
                fftStage += 1;
                fftP = 0;
                fftM >>= 1;
                fftS <<= 1;
                complex_t* tmp = fftSrc;
                fftSrc = fftDst;
                fftDst = tmp;
                if (fftStage >= 5) {
                    fftStage = 0;
                    fftM = 16;
                    fftS = 1;
                    fftBlock++;
                    fftSrc = fftTemp[fftBlock];
                }
            }
        }
        fftIfCal = 1;
    }

    uint32_t streamData = 0;
    switch (funct3) {
        case 0x02: //TODO:默认是 SSS-PP
            assert(fftCnt == 0 || fftCnt == 1);
            streamData = fftCnt == 0 ? fftAddRes.real : fftAddRes.imag;
            std::cout << "add! res is " << (int32_t)streamData << std::endl;
            result.wValid = true;
            result.wData = streamData;
            result.wIdx = fftCurE * 2 + fftCnt;
            fftCnt++;
            if (fftTag == 2) {
                fftTag = 0;
            }
            break;
        case 0x07:
            if (funct7 == 0x08) {//SSR STAGE0-3 SUB
                assert(fftCnt == 2 || fftCnt == 3);
                result.rdValid = true;
                result.rd = rd;
                result.rdData = fftCnt == 2 ? fftSubRes.real : fftSubRes.imag;
                std::cout << "sub! res is " << (int32_t)result.rdData << std::endl;
                fftCnt++;
                if (fftCnt == 4 && fftTag == 2) {
                    fftCnt = 0;
                    fftIfCal = 0;
                }
            } else {//SSR LAST STAGE ADD
                assert(funct7 == 0x00);
                assert(fftCnt == 0 || fftCnt == 1);
                result.rdValid = true;
                result.rd = rd;
                result.rdData = fftCnt == 0 ? fftAddRes.real : fftAddRes.imag;
                std::cout << "add_rd! res is " << (int32_t)result.rdData << std::endl;
                fftCnt++;
            }
            break;
        case 0x06: //TODO:RRS，默认是or
            assert(fftCnt == 4 || fftCnt == 5);
            if (fftStage == 4) {
                fftTag++;
                assert(fftTag <= 2);
            }
            streamData = fftCnt == 4 ? fftOrRes.real : fftOrRes.imag;
            std::cout << "OR! res is " << (int32_t)streamData << std::endl;
            result.wValid = true;
            result.wData = streamData;
            result.wIdx = fftCurO * 2 + (fftCnt - 4);
            fftCnt = fftCnt == 4 ? 5 : 0;
            if (fftCnt == 0) {
                fftIfCal = 0;
            }
            break;
        default:
            break;
    }

    return result;
}
