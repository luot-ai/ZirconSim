import csv

class Instruction:
    def __init__(self, id_in_file, seqnum, pc, disasm, is_branch):
        self.id = id_in_file
        self.seqnum = seqnum
        self.pc = pc
        self.disasm = disasm
        self.is_branch = is_branch
        self.stages = []  # list of (stage_name, start_tick, end_tick)
        self.retire_tick = None

    def add_stage(self, name, start, end):
        if end > start:
            self.stages.append((name, start, end))

def classify_instruction(asm):
    asm_lower = asm.lower()
    if asm_lower.startswith(("lb", "lh", "lw", "lbu", "lhu")):
        return "Load"
    elif asm_lower.startswith(("sb", "sh", "sw")):
        return "Store"
    elif asm_lower.startswith(("beq","bne","blt","bge","bltu","bgeu","jal","jalr")):
        return "Branch"
    elif asm_lower.startswith(("mul","div")):
        return "MulDiv"
    else:
        return "ALU"

def safe_int(val):
    if isinstance(val, list):
        val = val[0]
    val = str(val).strip()
    val = val.strip("[]'\"")
    return int(val)

def parse_csv(input_csv):
    instructions = []
    with open(input_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            instr = Instruction(
                id_in_file=idx,
                seqnum=idx,
                pc=row["pc"],
                disasm=row["asm"],
                is_branch=int(row.get("is_branch",0))
            )
            cyc = {k: safe_int(row[k]) for k in row if k not in ["pc","asm","is_branch"]}
            typ = classify_instruction(row["asm"])

            # pipeline stages
            instr.add_stage("F", cyc["fetch"], cyc["predecode"])
            instr.add_stage("PD", cyc["predecode"], cyc["decode"])
            instr.add_stage("D", cyc["decode"], cyc["dispatch"])
            instr.add_stage("IS", cyc["dispatch"], cyc["issue"])
            instr.add_stage("RF", cyc["issue"], cyc["readOp"])

            if typ in ["Load","Store"]:
                instr.add_stage("DC1", cyc["readOp"], cyc["exe"])
                instr.add_stage("DC2", cyc["exe"], cyc["exe1"])
                exe_end = cyc["exe1"]
            elif typ in ["MulDiv"]:
                instr.add_stage("EXE", cyc["readOp"], cyc["exe"])
                instr.add_stage("EXE1", cyc["exe"], cyc["exe1"])
                instr.add_stage("EXE2", cyc["exe1"], cyc["exe2"])
                exe_end = cyc["exe2"]
            else:  # ALU/Branch
                instr.add_stage("EXE", cyc["readOp"], cyc["exe"])
                exe_end = cyc["exe"]

            instr.add_stage("WB", exe_end, cyc["wb"])
            instr.retire_tick = cyc["retire"]

            instructions.append(instr)
    return instructions


def generate_kanata_log(instructions, output_file):
    min_tick = min(inst.stages[0][1] for inst in instructions)
    current_cycle = 0
    last_tick = None

    with open(output_file,'w',encoding='utf-8') as f:
        f.write("Kanata\t0004\n")
        f.write(f"C=\t{0}\n")

        all_events = []

        for inst in instructions:
            fetch_tick = inst.stages[0][1]
            all_events.append(("I", fetch_tick, inst))
            all_events.append(("L0",fetch_tick, inst))
            all_events.append(("L1",fetch_tick, inst))
            for stage_name, start, end in inst.stages:
                all_events.append(("S", start, inst, stage_name))
            if inst.retire_tick:
                all_events.append(("R", inst.retire_tick, inst))

        all_events.sort(key=lambda x: x[1])  # sort by tick

        last_tick = None
        ticks_per_cycle = 1
        for event in all_events:
            tick = event[1]
            cycle = (tick - min_tick) // ticks_per_cycle
            if last_tick is None:
                delta = cycle
            else:
                delta = cycle - current_cycle

            if delta > 0:
                f.write(f"C\t{delta}\n")
                current_cycle += delta
            last_tick = tick

            cmd = event[0]
            if cmd == "I":
                inst = event[2]
                f.write(f"I\t{inst.id}\t{inst.seqnum}\t0\n")
            elif cmd == "L0":
                inst = event[2]
                f.write(f"L\t{inst.id}\t0\t{inst.pc}: {inst.disasm}\n")
            elif cmd == "L1":
                inst = event[2]
                f.write(f"L\t{inst.id}\t1\tfetched @ tick {inst.stages[0][1]}\n")
            elif cmd == "S":
                inst = event[2]
                stage_name = event[3]
                f.write(f"S\t{inst.id}\t0\t{stage_name}\n")
            elif cmd == "E":
                inst = event[2]
                stage_name = event[3]
                f.write(f"E\t{inst.id}\t0\t{stage_name}\n")
            elif cmd == "R":
                inst = event[2]
                f.write(f"R\t{inst.id}\t{inst.id}\t0\n")  # type = 0: retire


if __name__ == "__main__":
    input_csv = "cfft.csv"
    output_log = "instructions.log"
    print("Converting CSV to Kanata format...")
    instructions = parse_csv(input_csv)
    generate_kanata_log(instructions, output_log)
    print(f"✅ Kanata log written to {output_log}")
