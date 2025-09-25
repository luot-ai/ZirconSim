WORK_DIR = $(abspath .)
VERILOG_DIR = $(WORK_DIR)/../verilog
CC_DIR = $(WORK_DIR)/src
BUILD_DIR = $(WORK_DIR)/build
TAR_DIR = $(BUILD_DIR)/obj


VERILOG_TOP 		= $(VERILOG_DIR)/CPU.sv
VFLAGS 				= --trace --cc --exe -O3 -I$(VERILOG_DIR) -Mdir $(BUILD_DIR) --no-MMD
VFLAGS 				+= -Wno-UNOPTFLAT -Wno-WIDTHEXPAND --verilate-jobs 8 
CINC_PATH 			= -CFLAGS -I$(WORK_DIR)/include

REWRITE = $(WORK_DIR)/script/rewrite.mk

CSRCS =  $(shell find $(CC_DIR) -name "*.cc")
VSRCS = $(shell find $(VERILOG_DIR) -name "*.sv")
BINARY = $(BUILD_DIR)/VCPU

IMG = 

COLOR_RED   		= \033[31m
COLOR_GREEN 		= \033[32m
COLOR_YELLOW 		= \033[33m
COLOR_BLUE  		= \033[34m
COLOR_PURPLE 		= \033[35m
COLOR_DBLUE 		= \033[36m
COLOR_NONE  		= \033[0m


SCALA_DIR = $(WORK_DIR)/../src/main/scala
SCALA_SRCS := $(shell find $(SCALA_DIR) -name "*.scala")


all: $(BINARY) 


$(BINARY): $(CSRCS) $(SCALA_SRCS)
	@printf "$(COLOR_YELLOW)[SCALA]$(COLOR_NONE) Zircon\n"
	@$(MAKE) -s -j32 -C ../ sim-verilog
	@printf "$(COLOR_DBLUE)[VERILATE]$(COLOR_NONE) $(notdir $(BUILD_DIR))/VCPU\n"
	@mkdir -p $(BUILD_DIR)
	@verilator $(VFLAGS) $(CSRCS) $(CINC_PATH) $(VERILOG_TOP)
	@printf "$(COLOR_DBLUE)[MAKE]$(COLOR_NONE) $(notdir $(BUILD_DIR))/VCPU\n"
	@$(MAKE) -s -j32 -C $(BUILD_DIR) -f $(REWRITE) 


run: $(BINARY) 
	@printf "$(COLOR_YELLOW)[RUN]$(COLOR_NONE) build/$(notdir $<)\n"
	@$(BINARY) $(IMG) $(ARGS)


clean:
	rm -rf $(BUILD_DIR)