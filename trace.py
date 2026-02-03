import csv
import sys
import os
import json
import string
from typing import List
from collections import defaultdict

useSaving = True
useHIpc = False


class Instruction:
    def __init__(self, seq, pc, asm, lastCmt, dispatch, ReadOp, Execute, writeBack, commit, is_branch):
        self.seq = int(seq)
        self.pc = pc
        self.asm = asm
        self.start = int(lastCmt)
        self.latency = int(commit) - int(lastCmt)
        self.dispatch = int(dispatch)
        self.ReadOp = int(ReadOp)
        self.Execute = int(Execute)
        self.writeBack = int(writeBack)
        self.commit = int(commit)
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
                "below_avg": ipc < 2 #avg_ipc +0.5
            })
        return infos

def classify_instruction(asm: str) -> str:
    """根据指令助记符分类"""
    asm_lower = asm.lower()
    if asm_lower.startswith(("lb", "lh", "lw", "lbu", "lhu")):
        return "Load"
    elif asm_lower.startswith(("sb", "sh", "sw")):
        return "Store"
    elif asm_lower.startswith(("beq", "bne", "blt", "bge", "bltu", "bgeu", "jal", "jalr")):
        return "Branch"
    elif asm_lower.startswith(("cal_stream")):
        return "CAL-STREAM"
    elif asm_lower.startswith(("step_i","cfg_")):
        return "MISC-STREAM"
    elif asm_lower.startswith(("mul")):
        return "multiply"
    else:
        return "Compute"

def output_instrview_json(instrs: List[Instruction], output_path="instrview.json"):
    """输出每条指令的时间段与类型信息"""
    instr_events = []
    for instr in instrs:
        # 基本字段
        event = {
            "name": instr.asm,
            "cname": "a",
            "ph": "X",
            "pid": "cpu",
            "tid": classify_instruction(instr.asm),
            "ts": instr.start,
            "dur": instr.latency,
        }
        instr_events.append(event)

    with open(output_path, "w") as f:
        json.dump(instr_events, f, indent=2)
    print(f"[+] Instruction-level trace written to {output_path}")


def analyze_instructions_by_pc(instructions, output_file="pc_stats.txt"):
    """
    根据 PC 分类统计指令性能，输出为逗号分隔格式（含 asm 和总 IPC）。
    """
    stats = defaultdict(lambda: {"total_cycles": 0.0, "count": 0, "asm": None})
    type_stats = defaultdict(lambda: {"total_cycles": 0.0, "count": 0})  # 新增
    total_cycles = 0.0

    # 聚合每条指令
    for inst in instructions:
        cycle = 1 / inst.ipc if inst.ipc > 0 else 0
        total_cycles += cycle

        # --- 按 PC 统计 ---
        if stats[inst.pc]["asm"] is None:
            stats[inst.pc]["asm"] = inst.asm
        stats[inst.pc]["total_cycles"] += cycle
        stats[inst.pc]["count"] += 1

        # --- 按类型统计 ---
        itype = classify_instruction(inst.asm)
        type_stats[itype]["total_cycles"] += cycle
        type_stats[itype]["count"] += 1

    # --- 按 total_cycles 从大到小排序 ---
    sorted_stats = sorted(stats.items(), key=lambda kv: kv[1]["total_cycles"], reverse=True)

    # --- 输出文件 ---
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("pc,asm,count,total_cycles,avg_cycles\n")
        for pc, data in sorted_stats:
            asm_safe = data["asm"].replace('"', '""')
            avg_cycles = data["total_cycles"] / data["count"] if data["count"] > 0 else 0
            f.write(f'{pc},"{asm_safe}",{data["count"]},{data["total_cycles"]:.6f},{avg_cycles:.6f}\n')

        f.write(f"\nTOTAL_Cycles,{total_cycles:.6f}\n\n")

        # --- 输出分类统计 ---
        f.write("Type,count,total_cycles,avg_cycles,save_cycles\n")
        for t, d in type_stats.items():
            avg_cycles = d["total_cycles"] / d["count"] if d["count"] > 0 else 0
            save_cycles = d['total_cycles'] - d["count"] / 2
            f.write(f"{t},{d['count']},{d['total_cycles']:.6f},{avg_cycles:.6f},{save_cycles:.1f}\n")

    print(f"✅ 已输出 {len(sorted_stats)} 条 PC 统计结果到 {output_file}")
    print(f"📊 所有指令 total_cycles 总和 = {total_cycles:.6f}")
    return sorted_stats, total_cycles, type_stats
def parse_trace_file(filename):
    instrs = []
    with open(filename, newline="") as f:
        reader = csv.reader(f)
        next(reader) 
        for seq, row in enumerate(reader):
            if not row:
                continue
            pc, asm, fetch, preDecode, decode, dispatch, issue, ReadOp, Execute,Execute1,Execute2, writeBack,writeBackROB, commit,lastCmt , is_branch = row[:16]
            instrs.append(Instruction(seq, pc, asm, lastCmt, dispatch, ReadOp, Execute, writeBack, commit, is_branch))

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

def analyze_pipeline_stages(instructions, output_file="pipeline_stage_stats.csv"):
    """
    统计每条指令从 lastCmtCycle 开始，到 commit 之间的流水级耗时（按 PC 聚合）。
    若相邻两条指令 commit 相同（同周期退休），则跳过后者。
    并按指令种类统计每个流水级耗时。
    """
    from collections import defaultdict

    stats = defaultdict(lambda: {"count": 0, "total_cycles": 0.0, "asm": None})
    stage_totals = defaultdict(float)  # 每个流水级总和
    stage_type_totals = defaultdict(lambda: defaultdict(float))  # stage -> type -> cycles

    if not instructions:
        print("⚠️ analyze_pipeline_stages: empty instruction list")
        return

    instrs = sorted(instructions, key=lambda x: x.seq)

    prev_commit = instrs[0].commit
    for inst in instrs[1:]:
        if inst.commit == prev_commit:
            prev_commit = inst.commit
            continue

        lc = inst.start
        d, rf, ex, wb, cm = inst.dispatch, inst.ReadOp, inst.Execute, inst.writeBack, inst.commit
        stage_durations = {}

        # 确定 lastCmt 所在阶段并计算各阶段耗时
        if lc < d:
            stage_durations["lastCmt->dispatch"] = d - lc
            stage_durations["dispatch->readop"] = rf - d
            stage_durations["readop->execute"] = ex - rf
            stage_durations["execute->writeback"] = wb - ex
            stage_durations["writeback->retire"] = cm - wb
        elif d <= lc < rf:
            stage_durations["dispatch->readop"] = rf - lc
            stage_durations["readop->execute"] = ex - rf
            stage_durations["execute->writeback"] = wb - ex
            stage_durations["writeback->retire"] = cm - wb
        elif rf <= lc < ex:
            stage_durations["readop->execute"] = ex - lc
            stage_durations["execute->writeback"] = wb - ex
            stage_durations["writeback->retire"] = cm - wb
        elif ex <= lc < wb:
            stage_durations["execute->writeback"] = wb - lc
            stage_durations["writeback->retire"] = cm - wb
        elif wb <= lc < cm:
            stage_durations["writeback->retire"] = cm - lc

        instr_type = classify_instruction(inst.asm)

        for stage, val in stage_durations.items():
            if val <= 0:
                continue
            # 按 PC 聚合
            key = (stage, inst.pc)
            entry = stats[key]
            if entry["asm"] is None:
                entry["asm"] = inst.asm
            entry["count"] += 1
            entry["total_cycles"] += val

            # 按流水级总和
            stage_totals[stage] += val
            # 按流水级+指令类型总和
            stage_type_totals[stage][instr_type] += val

        prev_commit = inst.commit

    # 输出 CSV
    rows = []
    for (stage, pc), data in stats.items():
        avg = data["total_cycles"] / data["count"] if data["count"] else 0
        rows.append((stage, pc, data["asm"], data["count"], data["total_cycles"], avg))

    rows.sort(key=lambda x: (x[0], -x[4]))

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Stage,PC,ASM,Count,Total_Cycles,Avg_Cycles\n")
        for stage, pc, asm, cnt, total, avg in rows:
            asm_safe = asm.replace('"', '""') if asm else ""
            f.write(f'{stage},{pc},"{asm_safe}",{cnt},{total:.3f},{avg:.3f}\n')

        # 输出每个流水级总和
        f.write("\n# Stage Totals\n")
        total_cycles_all = 0.0
        for stage, total in stage_totals.items():
            f.write(f'{stage}_TOTAL,{total:.3f}\n')
            total_cycles_all += total
        f.write(f'ALL_STAGES_TOTAL,{total_cycles_all:.3f}\n\n')

        # 输出每个流水级按指令类型的总和
        f.write("# Stage Totals by Instruction Type\n")
        for stage, type_dict in stage_type_totals.items():
            for instr_type, total in type_dict.items():
                f.write(f'{stage}_{instr_type}_TOTAL,{total:.3f}\n')

    print(f"✅ 输出文件: {output_file} （共 {len(rows)} 条统计）")
    print(f"📊 各流水级总和已附加，ALL_STAGES_TOTAL={total_cycles_all:.3f}")
  
def build_basic_blocks(instrs):
    """
    更稳健的 basic-block 构造：
    1) 先识别所有 block 起点（block_starts）：
       - 第 0 条指令一定是一个起点
       - 如果 instr[i].pc != instr[i-1].pc + 4（非顺序），则 instr[i] 是起点
       - 如果 instr[i-1] 是分支/跳转指令（instr[i-1].is_branch），则 instr[i] 也是起点
    2) 第二遍按起点切分：遇到起点就把上一个积累的 current_block 收尾并加入对应的 BasicBlock（按起点地址做 key）
    3) 保证每次到达某个起点都会产生一次迭代（即便只有 1 条指令）
    返回值：list(BasicBlock)，顺序是按首次出现顺序分配 block_id。
    """
    if not instrs:
        return []

    # 规范化 pc 字符串 (小写 hex)，避免大小写或格式问题
    def pc_norm(pc_str):
        return pc_str.lower()

    # 1) 识别所有 block 起点
    block_starts = set()
    block_starts.add(pc_norm(instrs[0].pc))
    for i in range(1, len(instrs)):
        prev = instrs[i-1]
        cur = instrs[i]
        try:
            expected = f"0x{int(prev.pc, 16) + 4:x}"
        except Exception:
            expected = None
        if expected is None or pc_norm(cur.pc) != expected:
            # 非顺序取指 -> 新起点（可能是跳转目标或异常/函数边界）
            block_starts.add(pc_norm(cur.pc))
        if prev.is_branch:
            # 上一条是分支/返回/跳转 -> 下一条也是起点（显式）
            block_starts.add(pc_norm(cur.pc))

    # 2) 第二遍按起点切分并收集 iterations
    blocks_map = {}           # key: start_pc -> BasicBlock
    block_id_counter = 0
    current_start = None
    current_block = []

    for instr in instrs:
        p = pc_norm(instr.pc)
        if p in block_starts:
            # 新起点出现：先把上一个积累的 block 关闭并加入对应 BasicBlock
            if current_block:
                # if instr.start == current_block[-1].start :
                #     print(instr.seq)
                if current_start not in blocks_map:
                    blocks_map[current_start] = BasicBlock(block_id_counter)
                    block_id_counter += 1
                blocks_map[current_start].add_iteration(current_block)
                if p != current_start:
                    print(blocks_map[current_start].block_id,"迭代次数：",len(blocks_map[current_start].iterations))
            # 启动一个新的 current_block，以当前 pc 作为 key
            current_start = p
            current_block = [instr]
        else:
            # 继续当前 block 的迭代
            current_block.append(instr)

    # 处理末尾残余
    if current_block:
        if current_start not in blocks_map:
            blocks_map[current_start] = BasicBlock(block_id_counter)
            block_id_counter += 1
        blocks_map[current_start].add_iteration(current_block)

    # 按首次出现顺序返回 blocks（blocks_map 的值已经按创建顺序分配 block_id）
    # 返回 list 按 block_id 排序，保证输出稳定
    blocks_list = sorted(blocks_map.values(), key=lambda b: b.block_id)
    return blocks_list
def dump_block_cycles_csv(blocks, output_csv):
    """
    输出每个基本块每次迭代的执行时间区间
    CSV 格式：
    block_id,iteration_id,start,end,cycles
    """
    with open(output_csv, "w", encoding="utf-8") as f:
        f.write("block_id,iteration_id,start,end,cycles\n")

        for bb in blocks:
            for it_id, it in enumerate(bb.iterations):
                if not it:
                    continue
                min_start = min(instr.start for instr in it)
                max_end   = max(instr.start + instr.latency for instr in it)
                cycles = (max_end - min_start)
                f.write(f"{bb.block_id},{it_id},{min_start},{max_end},{cycles}\n")

    print(f"✅ Block-level cycle CSV written to {output_csv}")

def main():
    imgname = sys.argv[1] + "-riscv32"
    trace_file = os.path.join("profiling", imgname, "base.log")
    output_dir = os.path.join("profiling", imgname)
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "blkinfo")
    view_file = os.path.join(output_dir, "blkview.json")  # 新增 view 文件
    instr_file =  os.path.join(output_dir, "instrview.csv")
    pipeline_file = os.path.join(output_dir, "pipeline_stage_stats.csv")

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
        if useSaving:
            #outfile.write("按预估优化收益排序的基本块（占比高于平均）:\n")
            avg_percent = 0 # 1 / 200 #len(blocks) if blocks else 0
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
            cumulative_cycles = 0
            block_savings.sort(key=lambda x: x[2], reverse=True)
            #block_savings.sort(key=lambda x: x[0].block_id, reverse=False)
            for bb, savings_percent, bb_cycles in block_savings:
                if savings_percent < avg_percent:
                    continue
                block_percent = bb_cycles / total_cycles * 100
                cumulative_percent += block_percent
                cumulative_cycles += bb_cycles
                outfile.write(
                    f"Block {bb.block_id}: 总cycles={bb_cycles}, 占比={(bb_cycles/total_cycles):.2f}, "
                    f"迭代次数 {len(bb.iterations)}, "
                    f"累计cycles={cumulative_cycles}, "
                    f"当前IPC={bb.avg_ipc():.2f}\n"
                )
        
        if useHIpc:
            for bb in blocks:
                bb_cycles = bb.total_cycles()
                it_infos = bb.iteration_info()
                it_infos.sort(key=lambda x: x["cycles"])  
                lowest_cycles = it_infos[0]['cycles']
                optimize_cycles = lowest_cycles * len(bb.iterations)
                save_cycles = bb_cycles - optimize_cycles
                if save_cycles / bb_cycles < 0.1 or bb_cycles / total_cycles < 0.02:
                    continue
                outfile.write(f"基本块 {bb.block_id}, 总耗时: {bb_cycles} cycles, 迭代次数: {len(bb.iterations)}, 平均IPC: {bb.avg_ipc():.2f}, 可优化周期: {save_cycles},占比: {(save_cycles / bb_cycles):.2f}\n")

        outfile.write("\n")
        # --- 详细基本块信息（按预估优化收益排序） ---
        for bb, savings_percent, bb_cycles in block_savings:
            if savings_percent < avg_percent:
                continue
            outfile.write(f"=== 基本块 {bb.block_id} ===\n")
            outfile.write(f"总耗时: {bb_cycles} cycles, 平均IPC: {bb.avg_ipc():.2f}\n")
            outfile.write(f"迭代次数: {len(bb.iterations)}\n")

            # block 内迭代按 IPC 从低到高排序
            it_infos = bb.iteration_info()
            it_infos.sort(key=lambda x: x["ipc"], reverse=True)  # 按 IPC 排序展示，但保留 iter_id
            cycles_dict = defaultdict(list)
            for info in it_infos:
                cycles_dict[info["cycles"]].append(info["iter_id"])
            for cycles in sorted(cycles_dict.keys()):
                iter_ids = " ".join(str(i) for i in sorted(cycles_dict[cycles]))
                outfile.write(f"    迭代 {iter_ids}, 耗时={cycles} cycles\n")
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

    # ========== 新增 blkview.json 输出 ==========
    colors = list(string.ascii_lowercase) 
    view_events = []
    for bb in blocks:
        for iter_idx, it in enumerate(bb.iterations, start=1):
            if not it:
                continue
            color = colors[(iter_idx - 1) % len(colors)]
            min_start = min(instr.start for instr in it)
            max_end = max(instr.start + instr.latency for instr in it)
            event = {
                "name": f"{color}: {iter_idx} Iter",
                "cname": color,   # 可换成 red/blue 等颜色
                "ph": "X",
                "pid": "cpu",
                "tid": f"Block {bb.block_id}",   # 每个迭代号作为 thread id
                "ts": min_start,
                "dur": max_end - min_start
            }
            view_events.append(event)
    with open(view_file, "w") as vf:
        json.dump(view_events, vf, indent=2)
    analyze_pipeline_stages(instrs,pipeline_file)

    #output_instrview_json(instrs,instr_file)
    analyze_instructions_by_pc(instrs,instr_file)

    block_csv = os.path.join(output_dir, "block_cycles.csv")
    dump_block_cycles_csv(blocks, block_csv)
if __name__ == "__main__":
    main()
