default: VCPU
include VCPU.mk
# CXX 		= clang++
CXXFLAGS 	+= -Os -fno-exceptions -fPIE -Wno-unused-result -fPIC -pipe -std=c++17
# LDFLAGS 	+= -rdynamic -fPIC
# LIBS 		+= 
# LINK 		= clang++