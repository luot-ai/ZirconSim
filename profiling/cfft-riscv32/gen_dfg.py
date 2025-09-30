import re

trace_file = "trace.txt"
output_md = "trace_flow.md"

nodes = []
edges = []

reg_re = r"a\d+"

def parse_instr(line):
    line = line.strip()
    if not line:
        return None
    m = re.match(r"(0x[0-9a-f]+)\s+(\w+)\s+(.+)", line)
    if not m:
        return None
    addr = m.group(1)
    instr = m.group(2)
    ops = [op.strip() for op in m.group(3).split(",")]
    return addr, instr, ops

last_written = {}

with open(trace_file) as f:
    for line in f:
        parsed = parse_instr(line)
        if not parsed:
            continue
        addr, instr, ops = parsed
        node_name = f"{addr}_{instr}"  # 单行节点名
        nodes.append(node_name)

        dest = None
        srcs = []

        if instr in ("lw", "add", "sub", "mul", "mulh", "sltu", "or"):
            dest = re.findall(reg_re, ops[0])
            dest = dest[0] if dest else None
            srcs = []
            for op in ops[1:]:
                srcs.extend(re.findall(reg_re, op))
        elif instr in ("sw",):
            srcs = re.findall(reg_re, ops[0])
            dest = "MEM"
        elif instr in ("bne",):
            srcs = re.findall(reg_re, ops[0])
            if len(ops) > 1:
                srcs += re.findall(reg_re, ops[1])
            dest = "BRANCH"
        elif instr in ("addi", "slli", "srli"):
            dest = re.findall(reg_re, ops[0])
            dest = dest[0] if dest else None
            srcs = re.findall(reg_re, ops[1]) if len(ops) > 1 else []

        for src in srcs:
            if src in last_written:
                edges.append((last_written[src], node_name))

        if dest:
            last_written[dest] = node_name

with open(output_md, "w") as f:
    f.write("```mermaid\nflowchart TD\n")
    for edge in edges:
        # 用双引号包裹节点名，避免特殊字符报错
        f.write(f'    {edge[0]} --> {edge[1]}\n')
    f.write("```\n")

print(f"生成完成: {output_md}")
