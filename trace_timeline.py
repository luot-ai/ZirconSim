import json
import sys
import os

# 访存类型映射
TYPE_MAP = {
    1: "STREAM",
    2: "INST",
    4: "DATA"
}

def parse_trace_line(line):
    parts = line.strip().split(',')
    if parts[0] == "start":
        return {"type": "start", "kind": int(parts[1]), "start": int(parts[2])}
    elif parts[0] == "end":
        return {"type": "end", "kind": int(parts[1]), "dur": int(parts[2]), "end": int(parts[3])}
    else:
        raise ValueError(f"Invalid line: {line}")

def convert_trace_to_json(trace_lines):
    results = []
    stack = []  # 暂存 start 记录
    type_count = {1: 0, 2: 0, 4: 0}  # 计数

    for line in trace_lines:
        if not line.strip():
            continue
        entry = parse_trace_line(line)

        if entry["type"] == "start":
            stack.append(entry)

        elif entry["type"] == "end":
            if not stack:
                print(f"⚠️ 无匹配的 start: {entry}")
                continue

            start_entry = stack.pop(0)  # FIFO 配对

            # 1️⃣ 检查类型匹配
            if start_entry["kind"] != entry["kind"]:
                print(f"❌ 类型不匹配: start={start_entry['kind']} end={entry['kind']}")
                continue

            # 2️⃣ 检查结束周期
            if entry["end"] != start_entry["start"] + entry["dur"] + 1:
                print(f"⚠️ 周期异常: start={start_entry['start']}, dur={entry['dur']}, end={entry['end']}")

            # 3️⃣ 生成 JSON 对象
            type_count[entry["kind"]] += 1
            obj = {
                "name": f"{TYPE_MAP[entry['kind']]}_{type_count[entry['kind']]}",
                "cname": "a",
                "ph": "X",
                "pid": "cpu",
                "tid": TYPE_MAP[entry["kind"]],
                "ts": start_entry["start"],
                "dur": entry["dur"]
            }
            results.append(obj)

    return results


def main():
    if len(sys.argv) < 2:
        print("用法: python3 trace_to_json.py trace.txt")
        sys.exit(1)

    trace_file = sys.argv[1]

    imgname = sys.argv[1] + "-riscv32"
    trace_file = os.path.join("profiling", imgname, "timeline.log")
    output_dir = os.path.join("profiling", imgname)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "timeline.json")

    with open(trace_file, 'r') as f:
        lines = f.readlines()

    json_data = convert_trace_to_json(lines)


    with open(output_file, 'w') as f:
        json.dump(json_data, f, indent=4)

    print(f"✅ 已生成 {output_file}，共 {len(json_data)} 条记录")


if __name__ == "__main__":
    main()
