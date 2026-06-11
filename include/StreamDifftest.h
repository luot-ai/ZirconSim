#ifndef STREAM_DIFFTEST_HH
#define STREAM_DIFFTEST_HH

#include <cstdint>
#include <string>
#include "AXIMemory.h"

enum class StreamDifftestMode {
    None,
    StreamAdd,
    Gemm,
    Fft32,
};

struct StreamDifftestResult {
    bool rdValid = false;
    uint8_t rd = 0;
    uint32_t rdData = 0;

    bool wValid = false;
    uint32_t wData = 0;
    uint32_t wIdx = 0;
};

class StreamDifftest {
    public:
    explicit StreamDifftest(StreamDifftestMode mode = StreamDifftestMode::None): mode(mode) {}

    static StreamDifftestMode modeFromString(const std::string& modeName);
    static StreamDifftestMode inferModeFromImage(const std::string& imgName);
    static const char* modeName(StreamDifftestMode mode);

    void setMode(StreamDifftestMode nextMode);
    StreamDifftestMode getMode() const { return mode; }
    StreamDifftestResult execute(uint32_t inst, uint32_t rf[32], AXIMemory* memory);

    private:
    struct GemmFifoConfig {
        uint32_t outer = 0;
        uint32_t length = 0;
        uint32_t limit = 0;
        uint32_t repeat = 0;
        uint32_t reuse = 0;
        uint32_t stride = 4;
        uint32_t tileStride = 0;
        uint32_t base = 0;
    };

    StreamDifftestMode mode = StreamDifftestMode::None;

    GemmFifoConfig gemmFifos[4];
    uint32_t gemmI = 0;
    uint32_t gemmJ = 0;
    uint32_t gemmK = 0;
    GemmFifoConfig addFifos[4];
    uint32_t addIndex = 0;

    StreamDifftestResult executeNone(uint32_t inst, uint32_t rf[32], AXIMemory* memory);
    StreamDifftestResult executeStreamAdd(uint32_t inst, uint32_t rf[32], AXIMemory* memory);
    StreamDifftestResult executeGemm(uint32_t inst, uint32_t rf[32], AXIMemory* memory);
    StreamDifftestResult executeFft32(uint32_t inst, uint32_t rf[32], AXIMemory* memory);

    void resetFft32();

    int fftBlock = 0;
    int fftStage = 0;
    int fftP = 0;
    int fftQ = 0;
    int fftCnt = 0;
    int fftM = 16;
    int fftS = 1;
    int fftIfCal = 0;
    int fftTotal = 0;
    int fftCurE = 0;
    int fftCurO = 0;
    int fftTag = 0;
};

#endif
