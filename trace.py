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
        self._ipc = None  # 延迟分配的 IPC（可能是 N/latency）

    @property
    def ipc(self):
        return self._ipc if self._ipc is not None else (1 / self.latency if self.latency > 0 else 0)

class BasicBlock:
    def __init__(self, block_id):
        self.block_id = block_id
        self.iterations = []  # 每次迭代是一组指令

    def add_iteration(self, instrs):
        self.iterations.append(instrs)

    def total_cycles(self):
        if not self.iterations:
            return 0
        total = 0
        for it in self.iterations:
            if not it:
                continue
            min_start = min(instr.start for instr in it)
            max_end   = max(instr.start + instr.latency for instr in it)
            total += (max_end - min_start)
        return total

    def avg_ipc(self):
        total_instrs = sum(len(it) for it in self.iterations)
        total_cycles = self.total_cycles()
        return total_instrs / total_cycles if total_cycles else 0

    def iteration_info(self):
        infos = []
        avg_ipc = self.avg_ipc()
        for idx, it in enumerate(self.iterations):
            if not it:
                continue
            min_start = min(instr.start for instr in it)
            max_end   = max(instr.start + instr.latency for instr in it)
            cycles = max_end - min_start
            ipc = len(it) / cycles if cycles else 0
            infos.append({
                "iter_id": idx + 1,  # 原始迭代号
                "cycles": cycles,
                "ipc": ipc,
                "instrs": it,   # 直接存 Instruction 对象
                "below_avg": ipc < avg_ipc +0.5
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

    # 调整 IPC：同一 start 的 N 条指令共享 latency
    start_groups = defaultdict(list)
    for instr in instrs:
        start_groups[instr.start].append(instr)

    for group in start_groups.values():
        n = len(group)
        if n == 0:
            continue
        latency = group[0].latency
        per_instr_ipc = n / latency if latency > 0 else 0
        for instr in group:
            instr._ipc = per_instr_ipc

    return instrs

def build_basic_blocks(instrs):
    blocks = {}
    block_id_counter = 0
    current_block_instrs = []

    def get_block_key(block_instrs):
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
            blocks[key].add_iteration(list(current_block_instrs))
            current_block_instrs = []

    if current_block_instrs:
        key = get_block_key(current_block_instrs)
        if key not in blocks:
            bb = BasicBlock(block_id_counter)
            block_id_counter += 1
            blocks[key] = bb
        blocks[key].add_iteration(list(current_block_instrs))

    return list(blocks.values())

def main():
    imgname = sys.argv[1]
    trace_file = os.path.join("profiling", imgname, "base.log")
    output_dir = os.path.join("profiling", imgname)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "blkinfo")

    instrs = parse_trace_file(trace_file)
    blocks = build_basic_blocks(instrs)

    total_cycles = 0
    if instrs:
        total_cycles = max(instr.start + instr.latency for instr in instrs) - min(instr.start for instr in instrs)
    overall_instrs = len(instrs)
    overall_ipc = overall_instrs / total_cycles if total_cycles else 0
    avg_cycles_per_block = total_cycles / len(blocks) if blocks else 0

    with open(output_file, "w") as outfile:
        outfile.write(f"程序的基本块数量: {len(blocks)}\n")
        outfile.write(f"总执行 cycles: {total_cycles}\n")
        outfile.write(f"总指令数: {overall_instrs}\n")
        outfile.write(f"总体 IPC: {overall_ipc:.2f}\n\n")

        sorted_blocks = sorted(blocks, key=lambda bb: bb.total_cycles(), reverse=True)
        # --- 粗略基本块信息（按预估优化收益排序） ---
        outfile.write("按预估优化收益排序的基本块（占比高于平均）:\n")
        avg_percent = 1 / 200 #len(blocks) if blocks else 0
        block_savings = []
        for bb in blocks:
            bb_instr_count = sum(len(it) for it in bb.iterations)
            bb_cycles = bb.total_cycles()
            # 预估优化 IPC = 2
            optimized_cycles = bb_instr_count / 2
            savings = bb_cycles - optimized_cycles
            savings_percent = savings / total_cycles if total_cycles else 0
            block_savings.append((bb, savings_percent, bb_cycles))
        # 按 savings_percent 排序
        cumulative_percent = 0.0
        block_savings.sort(key=lambda x: x[1], reverse=True)
        for bb, savings_percent, bb_cycles in block_savings:
            if savings_percent < avg_percent:
                continue
            block_percent = bb_cycles / total_cycles * 100
            cumulative_percent += block_percent
            outfile.write(
                f"Block {bb.block_id}: 原总cycles={bb_cycles}, "
                f"cycles占比={block_percent:.2f}%, "
                f"累计占比={cumulative_percent:.2f}%, "
                f"当前IPC={bb.avg_ipc():.2f}\n"
            )
        outfile.write("\n")
        #f"Block {bb.block_id}: 原总cycles={bb_cycles}, cycles占比={bb_cycles/total_cycles*100:.2f}%, 预估节省占比={savings_percent*100:.2f}%, 当前IPC={bb.avg_ipc():.2f}\n"
        # --- 详细基本块信息（按预估优化收益排序） ---
        for bb, savings_percent, bb_cycles in block_savings:
            if savings_percent < avg_percent:
                continue
            outfile.write(f"=== 基本块 {bb.block_id} ===\n")
            outfile.write(f"总耗时: {bb_cycles} cycles, 平均IPC: {bb.avg_ipc():.2f}\n")
            outfile.write(f"迭代次数: {len(bb.iterations)}\n")

            # block 内迭代按 IPC 从低到高排序
            it_infos = bb.iteration_info()
            it_infos.sort(key=lambda x: x["ipc"])  # 按 IPC 排序展示，但保留 iter_id
            for info in it_infos:
                if not info["below_avg"]:
                    continue
                outfile.write(f" 迭代 {info['iter_id']}: 耗时={info['cycles']} cycles, IPC={info['ipc']:.2f}\n")

                prev_start = None
                for instr in info["instrs"]:
                    pc_str = f"{instr.pc:<12}"
                    asm_str = f"{instr.asm:<30}"
                    start_str = f"start={instr.start:<5}"
                    delay_str = f"delay={instr.latency:<3}"

                    # 如果当前周期与上一条不同，则标记为第一条指令
                    mark = "*" if instr.start != prev_start else ""
                    prev_start = instr.start

                    outfile.write(f"    {pc_str} {asm_str} {start_str} {delay_str} {mark}\n")


if __name__ == "__main__":
    main()
