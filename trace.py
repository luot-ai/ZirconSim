import csv
import sys
import os

class Instruction:
    def __init__(self, seq, pc, asm, start, latency, is_branch):
        self.seq = int(seq)
        self.pc = pc
        self.asm = asm
        self.start = int(start)
        self.latency = int(latency)
        self.is_branch = bool(int(is_branch))
        #print(self.seq,self.pc,self.asm,self.start,self.latency,self.is_branch)

    @property
    def cpi(self):
        return self.latency  # 简化处理 CPI = latency

class BasicBlock:
    def __init__(self, block_id):
        self.block_id = block_id
        self.iterations = []  # 每次迭代是一组指令

    def add_iteration(self, instrs):
        self.iterations.append(instrs)

    def total_cycles(self):
        return sum(sum(instr.latency for instr in it) for it in self.iterations)

    def avg_cpi(self):
        total_instrs = sum(len(it) for it in self.iterations)
        return self.total_cycles() / total_instrs if total_instrs else 0

    def iteration_info(self):
        infos = []
        avg_cpi = self.avg_cpi()
        for it in self.iterations:
            cycles = sum(instr.latency for instr in it)
            cpi = cycles / len(it) if it else 0
            infos.append({
                "cycles": cycles,
                "cpi": cpi,
                "instrs": [(instr.pc, instr.asm, instr.cpi) for instr in it],
                "above_avg": cpi > avg_cpi  # 标记是否超过块内部平均CPI
            })
        return infos

def parse_trace_file(filename):
    instrs = []
    with open(filename, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            seq, pc, asm, start, latency, is_branch = row[:6]
            instrs.append(Instruction(seq, pc, asm, start, latency, is_branch))
    return instrs

def build_basic_blocks(instrs):
    """
    根据PC连续性和分支指令划分基本块
    同一块多轮迭代会汇总到同一个 BasicBlock
    """
    blocks = {}
    block_id_counter = 0
    current_block_instrs = []

    def get_block_key(block_instrs):
        # 用首条指令PC作为标识
        return block_instrs[0].pc if block_instrs else None

    for i, instr in enumerate(instrs):
        current_block_instrs.append(instr)
        end_block = False

        if instr.is_branch:
            end_block = True
        elif i + 1 < len(instrs):
            next_pc = instrs[i + 1].pc
            expected_pc = f"0x{int(instr.pc, 16) + 4:x}"
            if next_pc.lower() != expected_pc.lower():
                end_block = True

        if end_block:
            key = get_block_key(current_block_instrs)
            if key not in blocks:
                bb = BasicBlock(block_id_counter)
                block_id_counter += 1
                blocks[key] = bb
            else:
                bb = blocks[key]
            bb.add_iteration(list(current_block_instrs))
            current_block_instrs = []

    if current_block_instrs:
        key = get_block_key(current_block_instrs)
        if key not in blocks:
            bb = BasicBlock(block_id_counter)
            block_id_counter += 1
            blocks[key] = bb
        else:
            bb = blocks[key]
        bb.add_iteration(list(current_block_instrs))

    return list(blocks.values())

def main():
    imgname = sys.argv[1]
    trace_file = os.path.join("profiling", imgname, "base.log")
    output_dir = os.path.join("profiling", imgname)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "blkinfo")

    instrs = parse_trace_file(trace_file)
    blocks = build_basic_blocks(instrs)

    total_cycles = sum(bb.total_cycles() for bb in blocks)
    avg_cycles_per_block = total_cycles / len(blocks) if blocks else 0
    overall_instrs = sum(len(it) for bb in blocks for it in bb.iterations)
    overall_cpi = total_cycles / overall_instrs if overall_instrs else 0

    with open(output_file, "w") as outfile:
        outfile.write(f"程序的基本块数量: {len(blocks)}\n")
        outfile.write(f"总执行 cycles: {total_cycles}\n")
        outfile.write(f"总体 CPI: {overall_cpi:.2f}\n\n")

        # 按块总耗时降序排序
        sorted_blocks = sorted(blocks, key=lambda bb: bb.total_cycles(), reverse=True)

        for bb in sorted_blocks:
            bb_cycles = bb.total_cycles()
            if bb_cycles < avg_cycles_per_block:
                continue  # 只打印总耗时超过均值的块

            outfile.write(f"=== 基本块 {bb.block_id} ===\n")
            outfile.write(f"总耗时: {bb_cycles} cycles, 平均CPI: {bb.avg_cpi():.2f}\n")
            outfile.write(f"迭代次数: {len(bb.iterations)}\n")

            for it_id, info in enumerate(bb.iteration_info(), 1):
                if not info["above_avg"]:
                    continue  # 只打印迭代CPI超过块内部平均CPI的迭代
                outfile.write(f" 迭代 {it_id}: 耗时={info['cycles']} cycles, CPI={info['cpi']:.2f}\n")
                for pc, asm, cpi in info["instrs"]:
                    outfile.write(f"    {pc}  {asm}  CPI={cpi}\n")
            outfile.write("\n")

if __name__ == "__main__":
    main()
