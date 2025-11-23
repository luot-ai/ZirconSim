import json
import os
import re
import sys

# ============================
# Cache 配置
# ============================
CACHE_LEVELS = {
    "L1": {"OFFSET": 6, "INDEX": 4},
    "L2": {"OFFSET": 7, "INDEX": 5},
}


def line_addr(addr: int, offset_bits: int) -> str:
    line = addr >> offset_bits
    hex_line = f"0x{line:x}"      # 小写十六进制
    return f"\"{hex_line}\""


def get_index(addr, offset_bits, index_bits):
    return (addr >> offset_bits) & ((1 << index_bits) - 1)


def get_offset(addr, offset_bits):
    return addr & ((1 << offset_bits) - 1)


def process_trace(path, level_name, cfg):
    offset_bits = cfg["OFFSET"]
    index_bits = cfg["INDEX"]

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

        ts   = int(m.group(1))
        dur  = int(m.group(2))
        addr = int(m.group(3), 16)

        index  = get_index(addr, offset_bits, index_bits)
        offset = get_offset(addr, offset_bits)
        line_tag = line_addr(addr, offset_bits)

        event = {
            "name": f"{hex(addr)}, offset={offset}",
            "cname": level_name,
            "ph": "X",
            "pid": "cpu",
            "tid": index,
            "ts": ts,
            "dur": dur
        }

        events.append(event)

    return events


def main():
    imgname = sys.argv[1] + "-riscv32"
    trace_file = os.path.join("profiling", imgname, "cachelog.log")
    output_dir = os.path.join("profiling", imgname)

    for level_name, cfg in CACHE_LEVELS.items():
        events = process_trace(trace_file, level_name, cfg)

        output_file = os.path.join(output_dir, f"cache-trace-{level_name}.json")
        with open(output_file, "w") as f:
            json.dump(events, f, indent=2)

        print(f"[OK] {level_name} 写入 {output_file}，共 {len(events)} 条记录。")


if __name__ == "__main__":
    main()
