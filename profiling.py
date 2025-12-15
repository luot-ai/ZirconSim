#!/usr/bin/env python3
"""
stall_profiler.py (refactored)

使用静态 PC -> PC 依赖表（STATIC_DEP）做依赖判定并统计各类阻塞时间/次数。
按用户规则从 trace 的最后一条 sw 0x2e8 倒序扫描。

保存： stall_profiler.py
运行： python stall_profiler.py --input base.csv
"""

import csv
import argparse
from collections import defaultdict, Counter
from typing import List, Optional, Dict, Tuple

# ----------------------------
# CONFIG: 请根据你的 CSV 调整下面索引（如有必要）
# Header:
# pc,asm,fetch,predecode,decode,dispatch,issue,readOp,exe,exe1,exe2,wb,wbROB,retire,lastcommit,is_branch
# ----------------------------
CONFIG = {
    "strip_prefix": "0x80000",
    "COL_IDX": {
        # columns are 0-based for the numeric slice row[2:]
        # but our loader composes numeric list starting at original CSV col index 2 -> index 0 in nums
        # For simplicity we address by original CSV index here:
        "ASM_IDX": 1,
        "WBROB_IDX": 12, # wbROB (user indicated header "wbROB" at position 12)
        "WB_IDX": 11,   
        "RF_IDX": 7,    # readOp
        "D1_IDX": 8,    # exe / stage
        "D2_IDX": 9,    # exe1 / exe2 depending on your trace (you said exe2==1 for lsu)
    },
    "PC_GROUPS": {
        "mdu": {"26c","270","274","278","28c","290","294","298"},
        "lsu_output": {"25c","264","2bc","2c4"},
        "lsu_twiddle": {"260","268"},
        "sw_list": {"2d0","2d8","2e0","2e8"},
    },
    "MAX_LOOKBACK": 30,
    "LW_LOOKBACK": 10,
    "LW_MISS_L1_MAX": 10,
}

# ----------------------------
# STATIC DEPENDENCY TABLE
# Keys and values use PC suffix (no "0x80000" prefix).
# "external" means producer is outside this trace (don't search for it).
# You can extend/modify this mapping as needed.
# ----------------------------
STATIC_DEP = {
    "258": ["250", "23c"],
    "25c": ["258"],
    "260": ["2ec"],
    "264": ["258"],
    "268": ["2ec"],
    "26c": ["260","25c"],
    "270": ["260","25c"],
    "274": ["268","264"],
    "278": ["268","264"],
    "27c": ["270","278"],
    "280": ["26c","274"],
    "284": ["280","27c"],
    "288": ["270","278"],
    "28c": ["268","25c"],
    "290": ["268","25c"],
    "294": ["260","264"],
    "298": ["260","264"],
    "29c": ["290","298"],
    "2a0": ["28c","294"],
    "2a4": ["294","2a0"],
    "2a8": ["29c","2a4"],
    "2ac": ["284"],
    "2b0": ["288"],
    "2b4": ["2b0","2ac"],
    "2b8": ["2a8"],
    "2bc": ["2f0"],   # a30 external update often at 2f0; mark as producer if present
    "2c0": ["2a0"],
    "2c4": ["2f0"],   # depends on a30 external
    "2c8": ["2c0","2b8"],
    "2cc": ["2bc","2b4"],
    "2d0": ["2cc"],
    "2d4": ["2c4","2c8"],
    "2d8": ["2d4"],
    "2dc": ["2bc","2b4"],
    "2e0": ["2dc"],
    "2e4": ["2c4","2c8"],
    "2e8": ["2e4"],
    "2ec": ["external"],
    "2f0": ["external"],
    "2f4": ["2ec","external"],
    # add more if needed
}

# ----------------------------
# Utility helpers
# ----------------------------
def strip_pc(pc_full: str) -> str:
    p = pc_full.strip().lower()
    if p.startswith(CONFIG["strip_prefix"].lower()):
        return p[len(CONFIG["strip_prefix"]):]
    if p.startswith("0x8000"):
        return p[5:]
    if p.startswith("0x"):
        return p[2:]
    return p

def pc_to_suffix(pc: str) -> str:
    # input like "0x80000258" or "258" -> returns "258"
    return strip_pc(pc)

def inst_type_from_asm(asm: str, pc_suffix: str) -> str:
    a = asm.lower()
    if any(a.startswith(x) for x in ("mul","mulh","div","rem")) or pc_suffix in CONFIG["PC_GROUPS"]["mdu"]:
        return "mdu"
    if a.startswith("lw") or a.startswith("sw") or pc_suffix in CONFIG["PC_GROUPS"]["lsu_output"] or pc_suffix in CONFIG["PC_GROUPS"]["lsu_twiddle"]:
        return "lsu"
    if a.startswith(("b","jal","jalr")):
        return "branch"
    return "alu"

# ----------------------------
# Instruction representation
# ----------------------------
class Inst:
    def __init__(self, row: List[str], lineno:int):
        # row is a list from csv.reader
        self.raw_pc = row[0].strip()
        self.pc = pc_to_suffix(self.raw_pc)
        # asm in row[1] may contain quotes
        self.asm = row[1].strip().strip('"')
        # build numeric fields list aligning to original CSV indexes for easy idx access
        # We'll keep raw row and allow helpers to read numeric by column index
        self.row = row
        self.lineno = lineno
        self.type = inst_type_from_asm(self.asm, self.pc)

    def num_at(self, orig_idx: int) -> Optional[int]:
        # original CSV index: 0-based, so if orig_idx >= len(row) return None
        try:
            s = self.row[orig_idx].strip().strip('"')
            return int(s)
        except Exception:
            return None

    def rf(self) -> Optional[int]:
        return self.num_at(CONFIG["COL_IDX"]["RF_IDX"])
    
    def wbROB(self) -> Optional[int]:
        return self.num_at(CONFIG["COL_IDX"]["WBROB_IDX"])
    
    def wb(self) -> Optional[int]:
        return self.num_at(CONFIG["COL_IDX"]["WB_IDX"])

    def d1(self) -> Optional[int]:
        return self.num_at(CONFIG["COL_IDX"]["D1_IDX"])

    def d2(self) -> Optional[int]:
        return self.num_at(CONFIG["COL_IDX"]["D2_IDX"])

# ----------------------------
# Load trace
# ----------------------------
def load_trace(path: str) -> List[Inst]:
    insts: List[Inst] = []
    with open(path, newline='') as f:
        rdr = csv.reader(f)
        header = next(rdr)  # consume header
        for i,row in enumerate(rdr):
            if not row:
                continue
            insts.append(Inst(row, lineno=i+2))
    return insts

# ----------------------------
# Static-dep helpers
# ----------------------------
def get_static_producers(pc_suffix: str) -> List[str]:
    """Return list of producer pc_suffix strings (may include 'external')"""
    return STATIC_DEP.get(pc_suffix, [])

def find_prod_idx_for_pc(insts: List[Inst], prod_suffix: str, before_idx: int) -> Optional[int]:
    """
    Find the last occurrence index of producer PC suffix 'prod_suffix' that is strictly before before_idx.
    If producer is 'external', return None.
    """
    if prod_suffix == "external":
        return None
    if prod_suffix not in {inst.pc for inst in insts}:
        return None
    # find last occurrence with index < before_idx
    for j in range(before_idx-1, -1, -1):
        if insts[j].pc == prod_suffix:
            return j
    return None

def choose_nearest_prod(insts: List[Inst], prod_suffixes: List[str], cur_idx: int, max_back: int) -> Optional[Tuple[int,int]]:
    """
    Among the producer suffixes, choose the producer occurrence (index) that:
      - appears before cur_idx
      - within max_back window
      - yields smallest positive RF delta (cur_rf - prod_rf). Ties: choose later instruction (larger index).
    Returns (prod_idx, delta) or None.
    """
    cur_rf = insts[cur_idx].rf()
    if cur_rf is None:
        return None
    best = None  # (prod_idx, delta)
    for ps in prod_suffixes:
        if ps == "external":
            continue
        prod_idx = find_prod_idx_for_pc(insts, ps, cur_idx)
        if prod_idx is None:
            continue
        if cur_idx - prod_idx > max_back:
            continue
        prod_rf = insts[prod_idx].rf()
        if prod_rf is None:
            continue
        delta = cur_rf - prod_rf
        if delta < 0:
            continue
        if best is None or delta < best[1] or (delta == best[1] and prod_idx > best[0]):
            best = (prod_idx, delta)
    return best



# ----------------------------
# Main Profiler (static-dep driven)
# ----------------------------
class Profiler:
    def __init__(self, insts: List[Inst]):
        self.insts = insts
        self.pc_map = defaultdict(list)
        for i,ins in enumerate(insts):
            self.pc_map[ins.pc].append(i)

        self.counts = Counter()
        self.cycles = Counter()
        self.anomalies: List[str] = []
        self.breakpoints = set()
        self.curInst_seq: List[int] = []

    def add_cur_inst(self, idx: int):
        """添加到序列并打印"""
        print(f"[curInst_seq] appended: {idx}, pc {self.insts[idx].pc},asm {self.insts[idx].asm}")
        self.curInst_seq.append(idx)
    
    def add_anomaly(self, msg: str):
        print(f"[anomaly] {msg}")
        self.anomalies.append(msg)

    def find_last_sw_2e8(self) -> Optional[int]:
        if "2e8" not in self.pc_map:
            return None
        return self.pc_map["2e8"][-1]

    def classify_and_record(self, name:str, cyc:int=1):
        self.counts[name] += 1
        self.cycles[name] += cyc

    def run(self) -> Dict:
        start_idx = self.find_last_sw_2e8()
        if start_idx is None:
            raise RuntimeError("找不到 sw 0x2e8")
        idx = start_idx
        self.add_cur_inst(idx)
        print(f"Starting profiling from idx {idx} pc {self.insts[idx].pc}")

        # total fragment time
        wbs = [i.wbROB() for i in self.insts if i.wbROB() is not None]
        total_time = max(wbs) - min(wbs) if wbs else 0
        print(f"Total fragment time (wb max - wb min): {total_time}")
        
        # go backwards
        while idx >= 0:
            inst = self.insts[idx]
            pc = inst.pc
            typ = inst.type
            rf = inst.rf()

            # ---------- SW rules (specific)
            if pc in CONFIG["PC_GROUPS"]["sw_list"] and "sw" in inst.asm:
                if rf is None:
                    raise RuntimeError(f"not rf tick")
                
                # Step 1: find sw with rf+1 match within 10 instructions (both directions)
                prev_sw_idx = None
                # 往前看
                for j in range(idx - 1, max(idx - 10, -1), -1):
                    if self.insts[j].pc in CONFIG["PC_GROUPS"]["sw_list"] and "sw" in self.insts[j].asm:
                        prev_rf = self.insts[j].rf()
                        if prev_rf is not None and rf == prev_rf + 1:
                            prev_sw_idx = j
                            print(f"Found previous sw at idx {prev_sw_idx} pc {self.insts[prev_sw_idx].pc} with rf+1 match")
                            break
                # 往后看
                if prev_sw_idx is None:
                    for j in range(idx + 1, min(idx + 10 + 1, len(self.insts))):
                        if self.insts[j].pc in CONFIG["PC_GROUPS"]["sw_list"] and "sw" in self.insts[j].asm:
                            next_rf = self.insts[j].rf()
                            if next_rf is not None and rf == next_rf + 1:
                                prev_sw_idx = j
                                print(f"Found next sw at idx {prev_sw_idx} pc {self.insts[prev_sw_idx].pc} with rf+1 match")
                                break
                
                if prev_sw_idx is not None:
                    # found sw->sw part
                    self.classify_and_record("lsu_sw->sw_part", 1)
                    self.add_cur_inst(prev_sw_idx)
                    idx = prev_sw_idx
                else:
                    # Step 2: must be curInst == 2d8, check static producer 2d4
                    if pc != "2d8":
                        raise RuntimeError(f"not rf+1 match for non-2d8 sw at pc {pc}")
                    else:
                        # static producer: "2d4"
                        prod_list = get_static_producers(pc)
                        if "2d4" in prod_list:
                            chosen = choose_nearest_prod(self.insts, ["2d4"], idx, CONFIG["MAX_LOOKBACK"])
                            if chosen:
                                prod_idx, delta = chosen
                                prod_rf = self.insts[prod_idx].rf()
                                if prod_rf is not None and rf == prod_rf + 2:
                                    self.classify_and_record("data_alu->lsu_add->sw", 2)
                                    self.add_cur_inst(prod_idx)
                                    idx = prod_idx
                                else:
                                    self.add_anomaly(f"sw-2d8-check-fail at idx {idx} pc {pc}")
                                    idx -= 1
                            else:
                                self.add_anomaly(f"sw-2d8-no-producer found before pc {pc}")
                                idx -= 1
                        else:
                            self.add_anomaly(f"sw-2d8-no-2d4-in-static-dep at idx {idx} pc {pc}")
                            idx -= 1
                continue

            # ---------- ALU rules
            if typ == "alu":
                if rf is None:
                    raise RuntimeError(f"not rf tick")
                # static producers for this pc
                prod_suffixes = get_static_producers(pc)
                chosen = choose_nearest_prod(self.insts, prod_suffixes, idx, CONFIG["MAX_LOOKBACK"])
                if chosen is None:
                    self.breakpoints.add(pc)
                    # set curInst to most recent sw
                    for j in range(idx-1, -1, -1):
                        if self.insts[j].pc in CONFIG["PC_GROUPS"]["sw_list"]:
                            self.add_cur_inst(j)
                            print(f"[breakpoint] no producer found for alu pc {pc}, setting curInst to sw at idx {j} pc {self.insts[j].pc}")
                            break
                    idx = j
                    continue
                prod_idx, delta = chosen
                X = self.insts[prod_idx]
                self.add_cur_inst(prod_idx)
                # classify
                if X.type == "alu":
                    self.classify_and_record("data_alu->alu", 1)
                    if delta > 1:
                        self.add_anomaly(f"alu_long_delay pc {pc} <- {X.pc} delta {delta}")
                elif X.type == "mdu":
                    self.classify_and_record("data_mdu->alu", 3)
                    if delta > 4:
                        self.add_anomaly(f"mdu->alu_long pc {pc} <- {X.pc} delta {delta}")
                elif X.type == "lsu":
                    self.classify_and_record("data_lsu->alu", 1)
                    if delta > 2:
                        d1,d2 = X.d1(), X.d2()
                        if (d2 is not None and d2 <= 5) and (d1 is not None and d1 <= 5):
                            self.add_anomaly(f"alu_lw_unexpected_delay pc {pc} <- {X.pc} delta {delta}")
                else:
                    self.classify_and_record("data_other->alu", max(delta,0))
                idx = prod_idx
                continue

            # ---------- MDU rules
            if typ == "mdu":
                if rf is None:
                    raise RuntimeError(f"not rf tick")
                # check group single-issue: look up/down ±3 for any group member whose RF == this.rf -1
                found_group_part = False
                search_range = 10
                # 往上看：idx-1 到 max(idx-search_range, -1)
                for j in range(idx - 1, max(idx - search_range - 1, -1), -1):
                    if self.insts[j].pc in CONFIG["PC_GROUPS"]["mdu"]:
                        cand_rf = self.insts[j].rf()
                        if cand_rf is not None and (rf == cand_rf + 1 or rf == cand_rf + 2):
                            x = rf - cand_rf
                            self.classify_and_record("mdu_mul->mul_part", x)
                            self.add_cur_inst(j)
                            idx = j
                            found_group_part = True
                            break
                # 往下看：idx+1 到 min(idx+search_range, len(insts))
                if not found_group_part:
                    for j in range(idx + 1, min(idx + search_range + 1, len(self.insts))):
                        if self.insts[j].pc in CONFIG["PC_GROUPS"]["mdu"]:
                            cand_rf = self.insts[j].rf()
                            if cand_rf is not None and (rf == cand_rf + 1 or rf == cand_rf + 2):
                                x = rf - cand_rf
                                self.classify_and_record("mdu_mul->mul_part", x)
                                self.add_cur_inst(j)
                                idx = j
                                found_group_part = True
                                break
                if found_group_part:
                    if rf - self.insts[idx].rf() == 2:
                        self.add_anomaly(f"mdu_mul->mul_part_rf2 pc {pc} <- {self.insts[idx].pc}")#TODO:dispatch
                    continue
                # else, use static producers
                prod_suffixes = get_static_producers(pc)
                chosen = choose_nearest_prod(self.insts, prod_suffixes, idx, CONFIG["MAX_LOOKBACK"])
                if chosen is None:
                    raise RuntimeError(f"MDU cannot find dependency within {CONFIG['MAX_LOOKBACK']} for pc {pc}")
                prod_idx, delta = chosen
                X = self.insts[prod_idx]
                if X.type == "alu":
                    self.classify_and_record("data_alu->mdu", 4)
                    self.add_cur_inst(prod_idx)
                    if delta > 2:
                        self.add_anomaly(f"mdu_alu_long pc {pc} <- {X.pc} delta {delta}")
                elif X.type == "mdu":
                    raise RuntimeError(f"mdu->mdu dependency unexpected: {pc} <- {X.pc}")
                elif X.type == "lsu":
                    self.classify_and_record("data_lsu->mdu", 3)
                    self.add_cur_inst(prod_idx)
                    if delta > 2:
                        d1,d2 = X.d1(), X.d2()
                        if (d2 is not None and d2 <= 5) and (d1 is not None and d1 <= 5):
                            self.add_anomaly(f"mdu_lw_unexpected_delay pc {pc} <- {X.pc} delta {delta}")
                idx = prod_idx
                continue

            # ---------- LSU (lw/sw) rules
            if typ == "lsu":
                # handle loads and stores differently
                if "lw" in inst.asm:
                    # 1) cache miss check: D2 -> WB span (区分 output/twiddle 分别统计)
                    d2 = inst.d2()
                    wb = inst.wb()
                    group_suffix = None
                    if pc in CONFIG["PC_GROUPS"]["lsu_output"]:
                        group_suffix = "output"
                    elif pc in CONFIG["PC_GROUPS"]["lsu_twiddle"]:
                        group_suffix = "twiddle"
                    
                    if d2 is not None and wb is not None:
                        span = wb - d2
                        if span > 1:
                            if span <= CONFIG["LW_MISS_L1_MAX"]:
                                cache_type = f"cache_L1_miss_{group_suffix}" if group_suffix else "cache_L1_miss"
                                self.classify_and_record(cache_type, span)
                            else:
                                cache_type = f"cache_L2_miss_{group_suffix}" if group_suffix else "cache_L2_miss"
                                self.classify_and_record(cache_type, span)
                    
                    # 2) single-issue check within ±3: look for lw with RF == this.rf - 1
                    found_part = False
                    search_range = 3
                    # 往上看
                    for j in range(idx - 1, max(idx - search_range - 1, -1), -1):
                        if "lw" in self.insts[j].asm and self.insts[j].pc in (CONFIG["PC_GROUPS"]["lsu_output"] | CONFIG["PC_GROUPS"]["lsu_twiddle"]):
                            cand_rf = self.insts[j].rf()
                            if cand_rf is not None and rf is not None and rf == cand_rf + 1:
                                self.classify_and_record("lsu_lsu_part", 1)
                                found_part = True
                                self.add_cur_inst(j)
                                idx = j
                                break
                    # 往下看
                    if not found_part:
                        for j in range(idx + 1, min(idx + search_range + 1, len(self.insts))):
                            if "lw" in self.insts[j].asm and self.insts[j].pc in (CONFIG["PC_GROUPS"]["lsu_output"] | CONFIG["PC_GROUPS"]["lsu_twiddle"]):
                                cand_rf = self.insts[j].rf()
                                if cand_rf is not None and rf is not None and rf == cand_rf + 1:
                                    self.classify_and_record("lsu_lsu_part", 1)
                                    found_part = True
                                    self.add_cur_inst(j)
                                    idx = j
                                    break
                    
# filepath: [profiling.py](http://_vscodecontentref_/2)
                    if found_part:
                        continue
                    
                    # 3) check sw->lw: last sw 2e8 before idx
                    last_sw_2e8_idx = None
                    if "2e8" in self.pc_map:
                        lst = [i for i in self.pc_map["2e8"] if i < idx]
                        if lst:
                            last_sw_2e8_idx = lst[-1]
                    if last_sw_2e8_idx is not None and rf is not None:
                        sw_rf = self.insts[last_sw_2e8_idx].rf()
                        if sw_rf is not None and rf == sw_rf + 1:
                            self.classify_and_record("lsu_sw->lw_part", 1)
                            self.add_cur_inst(last_sw_2e8_idx)
                            idx = last_sw_2e8_idx
                            continue  # ← 添加这个！
                    
                    # 4) data dependency within 10 using STATIC_DEP
                    prod_suffixes = get_static_producers(pc)
                    chosen = choose_nearest_prod(self.insts, prod_suffixes, idx, CONFIG["LW_LOOKBACK"])
                    if chosen:
                        prod_idx, delta = chosen
                        X = self.insts[prod_idx]
                        if X.type == "alu":
                            if delta > 2:
                                raise RuntimeError(f"lw data delay >2 at pc {pc} <- {X.pc}")
                            self.classify_and_record("data_alu->lsu", 2)
                            self.add_cur_inst(prod_idx)
                            idx = prod_idx
                            continue
                        elif X.type == "mdu":
                            raise RuntimeError(f"lw <- mdu unexpected at {pc} <- {X.pc}")
                        elif X.type == "lsu":
                            raise RuntimeError(f"lw <- lsu unexpected at {pc} <- {X.pc}")
                    else:
                        if d2 is None or wb is None or (wb - d2) <= 1:
                            # no producer, no part, no miss -> breakpoint
                            self.breakpoints.add(pc)
                    
                    idx -= 1
                    continue
                elif "sw" in inst.asm:
                    # store handled by sw rule above; if not matched, still check static producer
                    prod_suffixes = get_static_producers(pc)
                    chosen = choose_nearest_prod(self.insts, prod_suffixes, idx, CONFIG["MAX_LOOKBACK"])
                    if chosen:
                        prod_idx, delta = chosen
                        # record data if it's alu->sw etc.
                        X = self.insts[prod_idx]
                        if X.type == "alu":
                            # expected delta 2 per your rule for specific case; we record delta
                            self.classify_and_record("data_alu->sw", delta)
                        else:
                            self.classify_and_record("data_other->sw", delta)
                        self.add_cur_inst(prod_idx)
                        idx = prod_idx
                        continue
                    else:
                        # nothing found -> leave
                        pass
                    idx -= 1
                    continue

            # branch / other
            if typ == "branch":
                # we cannot detect mispredict exactly; just count occurrences
                self.classify_and_record("branch", 0)
            idx -= 1

        # results
        return {
            "total_time": total_time,
            "counts": dict(self.counts),
            "cycles": dict(self.cycles),
            "anomalies": self.anomalies,
            "breakpoints": sorted(list(self.breakpoints)),
            "curInst_seq": self.curInst_seq
        }

# ----------------------------
# CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True, help="path to trace CSV (with header)")
    args = parser.parse_args()

    insts = load_trace(args.input)
    print(f"Loaded {len(insts)} instructions from {args.input}")
    prof = Profiler(insts)
    res = prof.run()

    print("\n===== Profiling Summary =====")
    print(f"Total fragment time (wb max - wb min): {res['total_time']}")
    print("\nCategory counts and cycles:")
    for k,v in sorted(res["counts"].items(), key=lambda x: -x[1]):
        cyc = res["cycles"].get(k, 0)
        print(f"{k:35s} count={v:6d}   cycles={cyc:6d}")
    if res["anomalies"]:
        print("\nAnomalies / odd cases:")
        for a in res["anomalies"]:
            print(" -", a)
    if res["breakpoints"]:
        print("\nBreakpoints (no dependency found within limit):")
        for b in res["breakpoints"]:
            print(" -", b)
    print("\ncurInst sequence (recorded pivots):", res["curInst_seq"])
    print("===== End =====\n")

if __name__ == "__main__":
    main()
