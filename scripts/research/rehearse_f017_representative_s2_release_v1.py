#!/usr/bin/env python3
"""Synthetic real-geometry rehearsal for the representative S2 release."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[2]
EXECUTOR=ROOT/"scripts/research/f017_representative_s2_executor_v1.py"
PYTHON=Path("/opt/homebrew/bin/python3.14")
ENV={**os.environ,"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1"}


def sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()


def main() -> int:
    s1=bytearray(24576); ffn=bytearray(49152)
    for index in range(6144):
        struct.pack_into("<f",s1,index*4,((index%97)-48)/4096.0)
        struct.pack_into("<d",ffn,index*8,((index%193)-96)/8192.0 + (2.0**-52 if index%2 else 0.0))
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); s1_path=root/"synthetic-s1.f32le"; ffn_path=root/"synthetic-ffn.f64le"
        s1_path.write_bytes(s1); ffn_path.write_bytes(ffn)
        outputs=[]; process_packets=[]
        for run in (1,2):
            output=root/f"s2-{run}.f32le"
            result=subprocess.run([str(PYTHON),str(EXECUTOR),"--synthetic-s1",str(s1_path),"--synthetic-ffn",str(ffn_path),"--output",str(output)],env=ENV,capture_output=True,text=True,check=False)
            if result.returncode != 0: raise RuntimeError(result.stderr)
            packet=json.loads(result.stdout); process_packets.append(packet); outputs.append(output.read_bytes())
        if outputs[0] != outputs[1]: raise RuntimeError("fresh process mismatch")
        protected=subprocess.run([sys.executable,"-m","unittest","scripts.research.tests.test_f017_representative_s2_release_v1","-v"],cwd=ROOT,capture_output=True,text=True,check=False)
        if protected.returncode != 0: raise RuntimeError(protected.stdout+protected.stderr)
    packet={
        "schema":"pulsarmlx.f017.representative-s2-synthetic-rehearsal",
        "schema_version":"1.0.0",
        "result":"PASS",
        "geometry":{"s1":{"dtype":"little-endian-f32","shape":[6144],"byte_length":24576},"ffn":{"dtype":"little-endian-f64","shape":[6144],"byte_length":49152},"s2":{"dtype":"little-endian-f32","shape":[6144],"byte_length":24576}},
        "synthetic_input_sha256":{"s1":sha(bytes(s1)),"ffn":sha(bytes(ffn))},
        "fresh_processes":2,
        "fresh_process_output_sha256":[packet["output_sha256"] for packet in process_packets],
        "exact_output_identity":"2_OF_2",
        "arithmetic_cases":{"exact_f32_to_f64_promotion":True,"binary64_addition":True,"ties_to_even_final_cast":True,"subnormal_not_flushed":True,"proof_reference_differs_from_serial_f32_discriminator":True},
        "release_mechanics":{"exclusive_attempt_race":"ONE_WINNER_ONE_LOSER","duplicate_attempt":"REJECTED","no_replace_publication":"PASS","descriptor_readback":"PASS","terminal_reconciliation":"PASS","race_loser_terminal_poisoning":"REJECTED_BY_OWNERSHIP_DESIGN"},
        "mutation_tests":"ALL_COMMITTED_MUTATIONS_REJECTED",
        "checkpoint_reads":0,"shard_opens":0,"real_s1_operand_consumptions":0,"real_ffn_operand_consumptions":0,"real_s2_constructions":0,"go_tokens_created":0,
    }
    print(json.dumps(packet,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__": raise SystemExit(main())
