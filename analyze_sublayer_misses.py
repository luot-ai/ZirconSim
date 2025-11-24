import csv, os, sys, json
from collections import defaultdict

# 配置（与之前一致）
GROUP_SIZE = 5120
SUB_SIZE = 512
SUB_COUNT = GROUP_SIZE // SUB_SIZE  # =10

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
        next(reader) 
        # 如果是没有表头直接开始也能工作
        for row in reader:
            if not row: continue
            # 兼容你给出的示例行（16 列或更多）
            # pc, asm, fetch, preDecode, decode, dispatch, issue, ReadOp, Execute,Execute1,Execute2, writeBack,writeBackROB, commit,lastCmt , is_branch
            # 我们只需要部分字段： pc, asm, dispatch, ReadOp, Execute, writeBack, commit, lastCmt, is_branch
            try:
                # 若行里 asm 含逗号可能被拆分；合并第1和第2列如果 asm 用双引号包围的情况被 csv 正确解析则不用担心
                pc = row[0].strip()
                asm = row[1].strip()
                # lastCmt 在样例中位置为 14（0-index 14），commit=13，dispatch=5, ReadOp=7, Execute=8, writeBack=11, is_branch=15
                # 以防输入列数变化，使用 try/except fallback
                dispatch = row[5]
                ReadOp = row[7]
                Execute = row[8]
                writeBack = row[11]
                commit = row[13]
                lastCmt = row[14]
                is_branch = row[15]
            except Exception:
                # 尝试截取前16列再解析
                cols = row + ["0"] * 16
                pc = cols[0].strip(); asm = cols[1].strip()
                dispatch = cols[5]; ReadOp = cols[7]; Execute = cols[8]
                writeBack = cols[11]; commit = cols[13]; lastCmt = cols[14]; is_branch = cols[15]
            instrs.append(Instruction(len(instrs), pc, asm, lastCmt, dispatch, ReadOp, Execute, writeBack, commit, is_branch))
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
        min_start = min(instr.start for instr in it)
        max_end = max(instr.start + instr.latency for instr in it)
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
            except:
                continue
            events.append({"ts": ts, "dur": dur})
    # 为加速查询按时间排序
    events.sort(key=lambda e: e["ts"])
    return events

# --------------------------
# 5) 统计每个小层的 miss count / miss_time
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

            # 统计 cache events 在 [layer_start, layer_end)
            miss_count = 0
            miss_dur_sum = 0
            # efficient scan: cache_events sorted by ts
            # binary search start index
            lo = 0; hi = len(cache_events)
            # find first index with ts >= layer_start
            while lo < hi:
                mid = (lo + hi)//2
                if cache_events[mid]["ts"] < layer_start:
                    lo = mid + 1
                else:
                    hi = mid
            idx = lo
            while idx < len(cache_events) and cache_events[idx]["ts"] < layer_end:
                miss_count += 1
                miss_dur_sum += cache_events[idx]["dur"]
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
                "occupancy_ratio": (miss_dur_sum / window_len) if window_len>0 else 0.0
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
        fout.write("block_id,group_idx,sub_idx_in_group,global_sub_index,iter_first,iter_last,start,end,window_len,miss_count,miss_dur_sum,occupancy_ratio\n")
        for blk in blocks:
            block_id = blk["block_id"]
            iterations = blk["iterations"]
            it_infos = iterations_to_infos(iterations)
            if not it_infos:
                continue
            results = analyze_sublayers_for_iteration_infos(it_infos, cache_events)
            for r in results:
                fout.write(f"{block_id},{r['group_idx']},{r['sub_idx_in_group']},{r['global_sub_index']},{r['iter_first']},{r['iter_last']},{r['start']},{r['end']},{r['window_len']},{r['miss_count']},{r['miss_dur_sum']:.0f},{r['occupancy_ratio']:.6f}\n")

    print(f"[+] 完成，输出：{out_csv}")

if __name__ == "__main__":
    main()
