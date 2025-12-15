#include "AXIMemory.h"

AXIMemory::AXIMemory(std::string imgPath, uint32_t baseAddr, Device* device) {
    this->device = device;

    if(imgPath.empty()) {
        memory.emplace(baseAddr >> 2, 0x80000000);
        refMemory.emplace(baseAddr >> 2, 0x80000000);
        return;
    } 
    // open binary file
    std::ifstream img(imgPath, std::ios::binary);
    if(!img.is_open()) {
        return;
    }
    // read binary file to memory
    uint32_t word;
    uint32_t addr = baseAddr >> 2;
    while(img.read(reinterpret_cast<char*>(&word), sizeof(uint32_t))) {
        memory[addr] = word;
        refMemory[addr] = word;
        addr += 1;
    }
    img.close();
    srand(time(NULL));
    // generate random sequence
    for(int i = 0; i < 1024; i++) {
        randSeq[i] = rand() % 4;
    }
}

uint8_t AXIMemory::nextRand() {
    uint8_t rand = randSeq[randSeqIndex];
    randSeqIndex = (randSeqIndex + 1) % 1024;
    return rand;
}

void AXIMemory::read(VCPU* cpu) {
    switch(readConfig.state) {
        case AXIReadState::IDLE: {
            cpu->io_axi_rvalid = 0;
            cpu->io_axi_rlast = 0;
            if(cpu->io_axi_arvalid) {
                readConfig.araddr = cpu->io_axi_araddr;
                readConfig.arlen = cpu->io_axi_arlen;
                readConfig.arsize = 1 << cpu->io_axi_arsize;
                readConfig.arburst = cpu->io_axi_arburst;
                readConfig.state = AXIReadState::AR;
            }
            break;
        }
        case AXIReadState::AR: {
            bool rand = nextRand() != 0;
            cpu->io_axi_arready = rand;
            if(rand && cpu->io_axi_arvalid) {
                readConfig.state = AXIReadState::R;
            }
            break;
        }
        case AXIReadState::R: {
            bool rand = nextRand() != 0;
            cpu->io_axi_arready = 0;
            cpu->io_axi_rvalid = rand;
            if(rand) {
                uint32_t wordAddr = readConfig.araddr >> 2;
                uint32_t wordOffset = readConfig.araddr & 0x3;
                uint32_t shiftAmount = wordOffset << 3;
                uint32_t word = memory[wordAddr] >> shiftAmount;
                cpu->io_axi_rdata = word;
                if(readConfig.arlen != 0) {
                    if(cpu->io_axi_rready) {
                        readConfig.arlen--;
                        readConfig.araddr += readConfig.arsize;
                    }
                } else {
                    cpu->io_axi_rlast = 1;
                    if(cpu->io_axi_rready) {
                        readConfig.state = AXIReadState::IDLE;
                    }
                }
            }
            break;
        }
        default: {
            break;
        }
    }
}


void AXIMemory::write(VCPU* cpu) {
    switch(writeConfig.state) {
        case AXIWriteState::IDLE: {
            cpu->io_axi_bvalid = 0;
            if(cpu->io_axi_awvalid) {
                writeConfig.awaddr = cpu->io_axi_awaddr;
                writeConfig.awlen = cpu->io_axi_awlen;
                writeConfig.awsize = 1 << cpu->io_axi_awsize;
                writeConfig.awburst = cpu->io_axi_awburst;
                writeConfig.wstrb = cpu->io_axi_wstrb;
                writeConfig.state = AXIWriteState::AW;
            }
            break;
        }
        case AXIWriteState::AW: {
            bool rand = nextRand() != 0;
            cpu->io_axi_awready = rand;
            if(rand && cpu->io_axi_awvalid) {
                writeConfig.state = AXIWriteState::W;
            }
            break;
        }
        case AXIWriteState::W: {
            bool rand = nextRand() != 0;
            cpu->io_axi_awready = 0;
            cpu->io_axi_wready = rand;
            if(rand && cpu->io_axi_wvalid) {
                uint32_t wordAddr = writeConfig.awaddr >> 2;
                uint32_t wordOffset = writeConfig.awaddr & 0x3;
                uint8_t wstrb = writeConfig.wstrb << wordOffset;
                if(wordAddr >> 26 == 0xa) {
                    device->write(writeConfig.awaddr, cpu->io_axi_wdata);
                } else {
                    uint32_t word = memory[wordAddr];
                    uint32_t wdataShift = cpu->io_axi_wdata << (wordOffset << 3);
                    for(int i = 0; i < 4; i++) {
                        if(wstrb & (1 << i)) {
                            word = (word & ~byteMasks[i]) | (wdataShift & byteMasks[i]);
                        }
                    }
                    memory[wordAddr] = word;
                }
                if(cpu->io_axi_wlast){
                    writeConfig.state = AXIWriteState::B;
                }
                writeConfig.awaddr += writeConfig.awsize;

            }
            break;
        }
        case AXIWriteState::B: {
            bool rand = nextRand() != 0;
            cpu->io_axi_wready = 0;
            cpu->io_axi_bvalid = rand;
            if(rand && cpu->io_axi_bready) {
                writeConfig.state = AXIWriteState::IDLE;
            }
            break;
        }
        default: {
            break;
        }
    }
}

uint32_t AXIMemory::refMemoryRead(uint32_t addr) {
    return refMemory[addr >> 2] >> ((addr & 0x3) << 3);
}

void AXIMemory::refMemoryWrite(uint32_t addr, uint32_t data, uint8_t wstrb) {
    uint32_t wordAddr = addr >> 2;
    uint32_t wordOffset = addr & 0x3;
    uint8_t wstrbShift = wstrb << wordOffset;
    uint32_t word = refMemory[wordAddr];
    uint32_t wdataShift = data << (wordOffset << 3);
    for(int i = 0; i < 4; i++) {
        if(wstrbShift & (1 << i)) {
            word = (word & ~byteMasks[i]) | (wdataShift & byteMasks[i]);
        }
    }
    refMemory[wordAddr] = word;
}

uint32_t AXIMemory::debugRead(uint32_t addr) {
    return memory[addr >> 2] >> ((addr & 0x3) << 3);
}