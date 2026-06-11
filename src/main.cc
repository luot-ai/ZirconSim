#include "verilated_vcd_c.h"
#include "VCPU.h"
#include "AXIMemory.h"
#include "Emulator.h"
#include "Device.h"
#include <iostream>
#include "utils.h"
#include "StreamDifftest.h"


int main(int argc, char** argv) {
    VCPU*cpu = new VCPU();
    VerilatedVcdC *vcd = new VerilatedVcdC();

    Verilated::traceEverOn(true);
    VerilatedVcdC *m_trace = new VerilatedVcdC;
    cpu->trace(m_trace, 5);
    m_trace->open("waveform.vcd");

    if (argc < 2) {
        std::cerr << "usage: " << argv[0] << " <image> [--stream-diff=none|stream-add|gemm|fft32]" << std::endl;
        return -1;
    }

    std::string imgPath = argv[1];

    Device *device = new Device();
    AXIMemory *memory = new AXIMemory(imgPath, 0x80000000, device);
    Statistic *stat = new Statistic();
    Simulator *simulator = new Simulator(memory);
    Emulator *emulator = new Emulator(cpu, memory, stat, simulator, m_trace);
    std::cout << "========================================" << std::endl;
    std::cout << ANSI_FG_CYAN << "SIMULATION STARTED." << ANSI_NONE << std::endl;

    emulator->reset();
    size_t slashPos = imgPath.find_last_of("/\\");
    size_t dotPos = imgPath.find_last_of('.');
    size_t nameStart = slashPos == std::string::npos ? 0 : slashPos + 1;
    size_t nameLen = dotPos == std::string::npos || dotPos < nameStart ? std::string::npos : dotPos - nameStart;
    std::string imgName = imgPath.substr(nameStart, nameLen);
    StreamDifftestMode streamMode = StreamDifftest::inferModeFromImage(imgName);
    for (int i = 2; i < argc; i++) {
        std::string arg = argv[i];
        const std::string prefix = "--stream-diff=";
        if (arg.rfind(prefix, 0) == 0) {
            streamMode = StreamDifftest::modeFromString(arg.substr(prefix.size()));
        }
    }
    simulator->setStreamDifftestMode(streamMode);
    std::cout << ANSI_FG_CYAN << "Stream difftest mode: "
              << StreamDifftest::modeName(streamMode) << ANSI_NONE << std::endl;
    int ret = emulator->step(-1,imgName);

    std::cout << "========================================" <<  std::endl;
    if(ret == -3) {
        std::cout << ANSI_FG_YELLOW<< "STALL FOR TOO LONG WITHOUT COMMITTING INSTRUCTIONS." << ANSI_NONE << std::endl;
    }else if(ret == -2) {
        std::cout << ANSI_FG_YELLOW << "DIFFTEST FAILED." << ANSI_NONE << std::endl;
    }else if(ret == -1) {
        std::cout << ANSI_FG_RED << "SIMULATION ENDED WITH a0 != 0." << ANSI_NONE << std::endl;
    }else if(ret == 0) {
        std::cout << ANSI_FG_GREEN << "SIMULATION ENDED SUCCESSFULLY." << ANSI_NONE << std::endl;
        
    }
    stat->printLastInstrucions(memory);
    stat->printPerformance();
    stat->printMarkdownReport(cpu, imgName, simulator);
    std::cout <<  "========================================" << std::endl;
    m_trace->close();
    return ret;
}