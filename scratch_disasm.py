import os as _kpos, sys as _kpsys
_kpsys.path.insert(0, _kpos.path.dirname(_kpos.path.abspath(__file__)))
import kitpaths as _kp
import subprocess, sys, os
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

import buildcfg

REPO = _kp.REPO
CC = buildcfg.CC
FLAGS = list(buildcfg.FLAGS)
os.chdir(REPO)
SRC = sys.argv[1]
OBJ = (_kp.SP + "/scratch_disasm.o")
r = subprocess.run([CC]+FLAGS+["-c", SRC, "-o", OBJ], capture_output=True, text=True)
if r.returncode != 0:
    print("COMPILE FAIL"); print(r.stdout[-2000:]); print(r.stderr[-2000:]); sys.exit(1)
elf = ELFFile(open(OBJ, "rb"))
texts = [s for s in elf.iter_sections() if s.name == ".text"]
data = b"".join(s.data() for s in texts)
print(f"total .text bytes: {len(data):#x} ({len(data)})")
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
for insn in md.disasm(data, 0):
    print(f"  +{insn.address:#06x}  {insn.mnemonic}\t{insn.op_str}")

# also show pristine
ADDR = int(sys.argv[2], 16)
SLOT = int(sys.argv[3], 16)
PRIST = open(f"{REPO}/{buildcfg.extract_root()}/arm9/arm9.bin", "rb").read()
BASE = 0x02000000
orig = PRIST[ADDR-BASE: ADDR-BASE+SLOT]
print("\npristine:")
for insn in md.disasm(orig, 0):
    print(f"  +{insn.address:#06x}  {insn.mnemonic}\t{insn.op_str}")
