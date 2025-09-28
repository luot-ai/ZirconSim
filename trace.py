import csv
import sys
import os
from collections import defaultdict

class Instruction:
    def __init__(self, seq, pc, asm, start, latency, is_branch):
        self.seq = int(seq)
        self.pc = pc
        self.asm = asm
        self.start = int(start)
        self.latency = int(latency)
        self.is_branch = bool(int(is_branch))

    @property
    def cpi(self):
        return self.latency  # 这里直接用 latency 表示 CPI


class BasicBlock:
    def __init__(self, block_id):
        self.block_id = block_id
        self.iterations = []  # 每次迭代是一组指令

    def add_iteration(self, instrs):
        self.iterations.append(instrs)

    def total_cycles(self):
        return sum(sum(instr.latency for instr in it) for it in self.iterations)

    def iteration_count(self):
        return len(self.iterations)

    def iteration_info(self):
        """返回每次迭代的耗时和CPI"""
        infos = []
        for it in self.iterations:
            cycles = sum(instr.latency for instr in it)
            cpi = cycles / len(it) if it else 0
            infos.append({
                "cycles": cycles,
                "cpi": cpi,
                "instrs": [(instr.pc, instr.asm, instr.cpi) for instr in it]
            })
        return infos

    def avg_cpi(self):
        total_instrs = sum(len(it) for it in self.iterations)
        return self.total_cycles() / total_instrs if total_instrs > 0 else 0


def parse_trace_file(filename):
    """解析 trace.csv -> list[Instruction]"""
    instrs = []
    with open(filename, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:  # 跳过空行
                continue
            seq, pc, asm, start, latency, is_branch = row[:6]
            instrs.append(Instruction(seq, pc, asm, start, latency, is_branch))
    return instrs


def build_basic_blocks(instrs):
    """根据PC连续性和分支指令划分基本块"""
    blocks = []
    block_id = 0
    current_block = []

    for i, instr in enumerate(instrs):
        current_block.append(instr)

        end_block = False
        if instr.is_branch:
            end_block = True
        elif i + 1 < len(instrs):
            next_pc = instrs[i + 1].pc
            expected_pc = f"0x{int(instr.pc, 16) + 4:x}"
            if next_pc.lower() != expected_pc.lower():
                end_block = True

        if end_block:
            bb = BasicBlock(block_id)
            bb.add_iteration(current_block)
            blocks.append(bb)
            block_id += 1
            current_block = []

    # 最后一块
    if current_block:
        bb = BasicBlock(block_id)
        bb.add_iteration(current_block)
        blocks.append(bb)

    return blocks

def main():
    imgname = sys.argv[1]
    trace_file = os.path.join("profiling", imgname, "base.log")
    output_dir = os.path.join("profiling", imgname)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "blkinfo")

    instrs = parse_trace_file(trace_file)
    blocks = build_basic_blocks(instrs)

    print(f"程序的基本块数量: {len(blocks)}")

    with open(output_file, "w") as outfile:
        outfile.write(f"程序的基本块数量: {len(blocks)}\n")

        # 计算每个块的总耗时
        block_cycles = [(bb, bb.total_cycles()) for bb in blocks]
        total_cycles = sum(c for _, c in block_cycles)

        # 按耗时排序，取前10
        block_cycles.sort(key=lambda x: x[1], reverse=True)
        top_blocks = block_cycles[:10]

        outfile.write("\n占比前10的基本块执行信息：\n")
        for rank, (bb, cyc) in enumerate(top_blocks, 1):
            outfile.write(f"\n=== 基本块 {bb.block_id} (排名 {rank}) ===\n")
            outfile.write(f"迭代次数: {bb.iteration_count()}\n")
            outfile.write(f"总耗时: {cyc} cycles\n")
            outfile.write(f"占比: {cyc/total_cycles:.2%}\n")
            outfile.write(f"平均CPI: {bb.avg_cpi():.2f}\n")

            # 打印每次迭代
            for it_id, info in enumerate(bb.iteration_info(), 1):
                outfile.write(f" 迭代 {it_id}: 耗时={info['cycles']} cycles, CPI={info['cpi']:.2f}\n")
                for pc, asm, cpi in info["instrs"]:
                    outfile.write(f"    {pc}  {asm}  CPI={cpi}\n")


if __name__ == "__main__":
    main()
