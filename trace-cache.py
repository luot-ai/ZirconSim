import json
import os
import re
import sys

# 配置
L1_OFFSET = 6
L1_INDEX  = 4

def line_addr(addr: int) -> str:
    line = addr #>> L1_OFFSET   # 去掉 offset bits
    hex_line = f"0x{line:x}"   # 转成十六进制（小写）
    return f"\"{hex_line}\""   # 带双引号

def get_index(addr):
    # index = addr[l1Index + l1Offset - 1 : l1Offset]
    # bits = [L1_OFFSET, L1_OFFSET + L1_INDEX)
    return (addr >> L1_OFFSET) & ((1 << L1_INDEX) - 1)

def get_offset(addr):
    # offset = addr[l1Offset-1 : 0]
    return addr & ((1 << L1_OFFSET) - 1)

def process_trace(path):
    events = []
    with open(path, "r") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 格式：9202,75,0x80001858
        m = re.match(r"(\d+),(\d+),0x([0-9a-fA-F]+)", line)
        if not m:
            continue

        ts = int(m.group(1))
        dur = int(m.group(2))
        addr = int(m.group(3), 16)

        index = get_index(addr)
        offset = get_offset(addr)
        line = line_addr(addr)

        event = {
            "name": f"{hex(addr)}, offset={offset}",
            "cname": "a",
            "ph": "X",
            "pid": "cpu",
            "tid": line,
            "ts": ts,
            "dur": dur
        }

        events.append(event)

    return events


def main():
    imgname = sys.argv[1] + "-riscv32"
    trace_file = os.path.join("profiling", imgname, "cachelog.log")
    output_dir = os.path.join("profiling", imgname)
    output_file = os.path.join(output_dir, "cache-trace.json")

    events = process_trace(trace_file)

    with open(output_file, "w") as f:
        json.dump(events, f, indent=2)

    print(f"已生成 {output_file}，共 {len(events)} 条记录。")


if __name__ == "__main__":
    main()
