import csv, os, sys, json
from collections import defaultdict

# 配置（与之前一致）
GROUP_SIZE = 5120
SUB_SIZE = 512
SUB_COUNT = GROUP_SIZE // SUB_SIZE  # =10

# twiddle 地址范围（包含端点）
START = 0x80000854
END   = 0x80001853

OSTART = 0x8000dfcc
OEND = 0x8000ffcb

# --------------------------
# 1) 解析指令 trace（与用户第一份格式）
# --------------------------
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
        self._ipc = None

def parse_instr_trace(filename):
    instrs = []
    with open(filename, newline='') as f:
        reader = csv.reader(f)
        # 尝试跳过表头（如果存在）
        try:
            first = next(reader)
            # 判断第一行是否为表头（包含非数字的 commit/lastCmt 字段）
            try:
                # 尝试把第14/13列转成 int，若失败则认为是表头
                int(first[13])
                int(first[14])
                # 如果没有异常，第一行是数据，需要把它作为第一条指令加入
                row0 = first
                # 处理 row0
                cols = row0 + ["0"] * 16
                pc = cols[0].strip(); asm = cols[1].strip()
                dispatch = cols[5]; ReadOp = cols[7]; Execute = cols[8]
                writeBack = cols[11]; commit = cols[13]; lastCmt = cols[14]; is_branch = cols[15]
                instrs.append(Instruction(len(instrs), pc, asm, lastCmt, dispatch, ReadOp, Execute, writeBack, commit, is_branch))
            except Exception:
                # 第一行是表头，继续从 reader 迭代真实数据
                pass
        except StopIteration:
            return instrs

        for row in reader:
            if not row: continue
            try:
                pc = row[0].strip()
                asm = row[1].strip()
                dispatch = row[5]
                ReadOp = row[7]
                Execute = row[8]
                writeBack = row[11]
                commit = row[13]
                lastCmt = row[14]
                is_branch = row[15]
            except Exception:
                cols = row + ["0"] * 16
                pc = cols[0].strip(); asm = cols[1].strip()
                dispatch = cols[5]; ReadOp = cols[7]; Execute = cols[8]
                writeBack = cols[11]; commit = cols[13]; lastCmt = cols[14]; is_branch = cols[15]
            # 有可能某些行仍是损坏的，保护性 try
            try:
                instrs.append(Instruction(len(instrs), pc, asm, lastCmt, dispatch, ReadOp, Execute, writeBack, commit, is_branch))
            except Exception:
                # 跳过无法解析的行
                continue
    return instrs

# --------------------------
# 2) 构建 basic blocks（复用你原逻辑）
# --------------------------
def pc_norm(pc_str):
    return pc_str.lower()

def build_basic_blocks(instrs):
    if not instrs: return []
    block_starts = set()
    block_starts.add(pc_norm(instrs[0].pc))
    for i in range(1, len(instrs)):
        prev = instrs[i-1]; cur = instrs[i]
        try:
            expected = f"0x{int(prev.pc, 16) + 4:x}"
        except Exception:
            expected = None
        if expected is None or pc_norm(cur.pc) != expected:
            block_starts.add(pc_norm(cur.pc))
        if prev.is_branch:
            block_starts.add(pc_norm(cur.pc))

    blocks_map = {}
    block_id_counter = 0
    current_start = None
    current_block = []
    for instr in instrs:
        p = pc_norm(instr.pc)
        if p in block_starts:
            if current_block:
                if current_start not in blocks_map:
                    blocks_map[current_start] = {"block_id": block_id_counter, "iterations": []}
                    block_id_counter += 1
                blocks_map[current_start]["iterations"].append(current_block)
            current_start = p
            current_block = [instr]
        else:
            current_block.append(instr)
    if current_block:
        if current_start not in blocks_map:
            blocks_map[current_start] = {"block_id": block_id_counter, "iterations": []}
            block_id_counter += 1
        blocks_map[current_start]["iterations"].append(current_block)

    blocks_list = [blocks_map[k] for k in sorted(blocks_map.keys(), key=lambda k: blocks_map[k]["block_id"])]
    return blocks_list

# --------------------------
# 3) 为每次迭代收集 start/end/cycles
# --------------------------
def iterations_to_infos(iterations):
    infos = []
    for idx, it in enumerate(iterations):
        if not it: continue
        try:
            min_start = min(instr.start for instr in it)
            max_end = max(instr.start + instr.latency for instr in it)
        except Exception:
            continue
        cycles = max_end - min_start
        infos.append({
            "iter_id": idx + 1,
            "start": min_start,
            "end": max_end,
            "cycles": cycles,
            "instrs": it
        })
    return infos

# --------------------------
# 4) 解析 cache miss trace（ts,dur,0xaddr）
# --------------------------
def parse_cache_trace(filename):
    events = []
    with open(filename, "r") as f:
        for line in f:
            s = line.strip()
            if not s: continue
            parts = s.split(",")
            if len(parts) < 3: continue
            try:
                ts = int(parts[0])
                dur = int(parts[1])
                # 解析地址，允许 0x 前缀或不带
                addr_str = parts[2].strip()
                # 有时 addr 前后可能带空格或有其他字段，尝试仅取 0x... 部分
                if addr_str.startswith("0x") or addr_str.startswith("0X"):
                    addr = int(addr_str, 16)
                else:
                    # 可能是 "0x8000e044" 带其它字符，尝试直接转换
                    addr = int(addr_str, 16)
            except Exception:
                # 若无法解析 addr 或数值，跳过此条 cache event
                continue
            events.append({"ts": ts, "dur": dur, "addr": addr})
    # 为加速查询按时间排序
    events.sort(key=lambda e: e["ts"])
    return events

# --------------------------
# 5) 统计每个小层的 miss count / miss_time（并拆分 twiddle/output 与 L1/L2）
# --------------------------
def analyze_sublayers_for_iteration_infos(it_infos, cache_events, group_size=GROUP_SIZE, sub_size=SUB_SIZE):
    results = []  # list of dicts per sublayer
    total_iters = len(it_infos)
    # 遍历每个大组
    for g_start in range(0, total_iters, group_size):
        g_end = min(g_start + group_size, total_iters)
        group = it_infos[g_start:g_end]
        # 每组切成 sub_count 个小层
        for sub_id in range( (len(group) + sub_size -1) // sub_size ):  # handle partial last group
            s_start = sub_id * sub_size
            s_end = min(s_start + sub_size, len(group))
            sub = group[s_start:s_end]
            if not sub:
                continue
            # 小层时间窗用首尾 iteration 的 start/end
            layer_start = sub[0]["start"]
            layer_end = sub[-1]["end"]
            window_len = layer_end - layer_start if layer_end > layer_start else 0

            # 初始化统计量
            miss_count = 0
            miss_dur_sum = 0

            # twiddle/output × L1/L2 的计数与时长
            tw_l1 = 0; tw_l1_dur = 0
            tw_l2 = 0; tw_l2_dur = 0
            out_l1 = 0; out_l1_dur = 0
            out_l2 = 0; out_l2_dur = 0
            miss_taken_l1 = 0; miss_taken_l1_dur = 0
            miss_taken_l2 = 0; miss_taken_l2_dur = 0
            # efficient scan: cache_events sorted by ts
            # binary search start index
            lo = 0; hi = len(cache_events)
            while lo < hi:
                mid = (lo + hi)//2
                if cache_events[mid]["ts"] < layer_start:
                    lo = mid + 1
                else:
                    hi = mid
            idx = lo
            # 遍历属于该 window 的 cache events
            while idx < len(cache_events) and cache_events[idx]["ts"] < layer_end:
                ev = cache_events[idx]
                miss_count += 1
                miss_dur_sum += ev["dur"]

                # 判定 twiddle / output
                addr = ev.get("addr")
                is_twiddle = (addr is not None and START <= addr <= END)
                is_output = (addr is not None and OSTART <= addr <= OEND)
                # 判定 L1 / L2
                is_l2 = (ev.get("dur", 0) > 10)

                # 累计到对应 bucket
                if is_twiddle:
                    if is_l2:
                        tw_l2 += 1
                        tw_l2_dur += ev["dur"]
                    else:
                        tw_l1 += 1
                        tw_l1_dur += ev["dur"]
                elif is_output:
                    if is_l2:
                        out_l2 += 1
                        out_l2_dur += ev["dur"]
                    else:
                        out_l1 += 1
                        out_l1_dur += ev["dur"]
                else:
                    if is_l2:
                        miss_taken_l2 += 1
                        miss_taken_l2_dur += ev["dur"]
                    else:
                        miss_taken_l1 += 1
                        miss_taken_l1_dur += ev["dur"]

                idx += 1

            results.append({
                "group_idx": g_start // group_size,
                "sub_idx_in_group": sub_id,
                "global_sub_index": (g_start // group_size) * SUB_COUNT + sub_id,
                "iter_first": sub[0]["iter_id"],
                "iter_last": sub[-1]["iter_id"],
                "start": layer_start,
                "end": layer_end,
                "window_len": window_len,
                "miss_count": miss_count,
                "miss_dur_sum": miss_dur_sum,
                "occupancy_ratio": (miss_dur_sum / window_len) if window_len>0 else 0.0,
                # 新增细分
                "tw_l1": tw_l1,
                "tw_l1_dur": tw_l1_dur,
                "tw_l2": tw_l2,
                "tw_l2_dur": tw_l2_dur,
                "out_l1": out_l1,
                "out_l1_dur": out_l1_dur,
                "out_l2": out_l2,
                "out_l2_dur": out_l2_dur,
                "miss_taken_l1": miss_taken_l1,
                "miss_taken_l1_dur": miss_taken_l1_dur,
                "miss_taken_l2": miss_taken_l2,         
                "miss_taken_l2_dur": miss_taken_l2_dur
            })
    return results

# --------------------------
# 6) main
# --------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_sublayer_misses.py <imgname>")
        sys.exit(1)
    imgname = sys.argv[1] + "-riscv32"
    instr_trace = os.path.join("profiling", imgname, "base.log")   # 你的第一份trace
    cache_trace = os.path.join("profiling", imgname, "cachelog.log")  # 你的第二份trace
    out_csv = os.path.join("profiling", imgname, "sublayer_miss_stats.csv")

    print("[*] 解析指令 trace ...")
    instrs = parse_instr_trace(instr_trace)
    blocks = build_basic_blocks(instrs)
    print(f"[*] 发现 basic blocks: {len(blocks)}")

    print("[*] 解析 cache trace ...")
    cache_events = parse_cache_trace(cache_trace)
    print(f"[*] cache events: {len(cache_events)}")

    # 对每个 block 输出其每个小层统计（可选：只分析 top-k blocks）
    with open(out_csv, "w", encoding="utf-8") as fout:
        fout.write(
            "block_id,group_idx,sub_idx_in_group,global_sub_index,iter_first,iter_last,"
            "start,end,window_len,miss_count,miss_dur_sum,occupancy_ratio,"
            "tw_l1,tw_l1_dur,tw_l2,tw_l2_dur,out_l1,out_l1_dur,out_l2,out_l2_dur,miss_taken_l1, miss_taken_l1_dur,miss_taken_l2, miss_taken_l2_dur \n"
        )
        for blk in blocks:
            block_id = blk["block_id"]
            iterations = blk["iterations"]
            it_infos = iterations_to_infos(iterations)
            if not it_infos:
                continue
            results = analyze_sublayers_for_iteration_infos(it_infos, cache_events)
            for r in results:
                fout.write(
                    f"{block_id},{r['group_idx']},{r['sub_idx_in_group']},{r['global_sub_index']},"
                    f"{r['iter_first']},{r['iter_last']},{r['start']},{r['end']},{r['window_len']},"
                    f"{r['miss_count']},{r['miss_dur_sum']:.0f},{r['occupancy_ratio']:.6f},"
                    f"{r['tw_l1']},{r['tw_l1_dur']:.0f},{r['tw_l2']},{r['tw_l2_dur']:.0f},"
                    f"{r['out_l1']},{r['out_l1_dur']:.0f},{r['out_l2']},{r['out_l2_dur']:.0f},"
                    f"{r['miss_taken_l1']},{r['miss_taken_l1_dur']:.0f},{r['miss_taken_l2']},{r['miss_taken_l2_dur']:.0f}\n"
                )

    print(f"[+] 完成，输出：{out_csv}")

if __name__ == "__main__":
    main()
