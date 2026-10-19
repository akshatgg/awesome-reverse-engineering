"""Build firmware.c for the LM3S6965, run ripcord's ELF pipeline and a Renode trace, and check the warehouse against known facts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
TARGET = "ripcord_fixture"
CONFIG = f"""
  {TARGET}:
    elf: targets/{TARGET}/{TARGET}.elf
    description: "Self-authored LM3S6965 UART0 fixture, Cortex-M3, clang -O1"
    arch: arm
    build_tuple: m3-clang-O1-freestanding
    source: "awesome-reverse-engineering examples/resource-intake/ripcord/firmware.c"
    svd: targets/_svd/LM3S6965.svd
"""
# Same commands as ripcord's renode_trace rule, with Renode's $CWD left literal.
RESC = f"""mach create
machine LoadPlatformDescription @scripts/renode/lm3s6965.repl
sysbus LoadELF @targets/{TARGET}/{TARGET}.elf
showAnalyzer uart0
logLevel -1 sysbus
logFile $CWD/build/{TARGET}/traces/boot.log true
cpu CreateExecutionTracing "tracer" $CWD/build/{TARGET}/traces/boot.trace PCAndOpcode
tracer TrackMemoryAccesses
emulation RunFor "0:0:0.1"
quit
"""
FUNCTIONS = ["default_handler", "fixture_checksum", "reset_handler", "uart_init", "uart_putc", "uart_puthex16", "uart_puts"]
CALLS = [["reset_handler", "fixture_checksum"], ["reset_handler", "uart_init"], ["reset_handler", "uart_puthex16"],
         ["reset_handler", "uart_puts"], ["uart_puthex16", "uart_putc"], ["uart_puthex16", "uart_putc"], ["uart_puts", "uart_putc"]]
PERIPHERAL_XREFS = [["uart_init", "READ", "SYSCTL", "RCGC1"], ["uart_init", "WRITE", "SYSCTL", "RCGC1"],
                    ["uart_init", "WRITE", "UART0", "CTL"], ["uart_putc", "READ", "UART0", "FR"], ["uart_putc", "WRITE", "UART0", "DR"]]
MMIO = [["uart_init", "read", "sysctl", 1], ["uart_init", "write", "sysctl", 1], ["uart_init", "write", "uart0", 1],
        ["uart_putc", "read", "uart0", 21], ["uart_putc", "write", "uart0", 21]]


def run(*args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ripcord", type=Path, required=True, help="ripcord checkout at the pinned commit, after uv sync --frozen")
    parser.add_argument("--renode", required=True, help="Renode executable")
    parser.add_argument("--pyghidra", required=True, help="Ghidra support/pyghidraRun")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, build = args.ripcord.resolve(), args.output.resolve()
    build.mkdir(parents=True, exist_ok=True)
    obj, elf = build / "firmware.o", build / f"{TARGET}.elf"
    run("clang", "--target=thumbv7m-none-eabi", "-mcpu=cortex-m3", "-O1", "-ffreestanding", "-fno-builtin", "-nostdlib",
        "-c", str(SOURCE / "firmware.c"), "-o", str(obj))
    run("ld.lld", "-T", str(SOURCE / "link.ld"), str(obj), "-o", str(elf))

    config = repo / "config.yaml"
    if f"  {TARGET}:" not in config.read_text():
        config.write_text(config.read_text().rstrip("\n") + "\n" + CONFIG)
    shutil.rmtree(repo / "build" / TARGET, ignore_errors=True)
    env = dict(os.environ, GHIDRA_PYGHIDRA=args.pyghidra)
    run("uv", "run", "python", "scripts/ripcord.py", str(elf), "--chip", "LM3S6965", "--name", TARGET, "--no-open", cwd=repo, env=env)

    (repo / "build" / TARGET / "traces").mkdir(parents=True)
    resc = build / "boot.resc"
    resc.write_text(RESC)
    console = subprocess.run([args.renode, "--disable-xwt", "--console", str(resc)], cwd=repo, stdin=subprocess.DEVNULL,
                             check=True, text=True, capture_output=True).stdout
    jsonl, tables = f"build/{TARGET}/mmio_events_boot.jsonl", f"build/{TARGET}/tables"
    run("uv", "run", "python", "scripts/renode/parse_trace.py", "--trace", f"build/{TARGET}/traces/boot.trace",
        "--scenario", "boot", "--output", jsonl, cwd=repo)
    run("uv", "run", "python", "scripts/ingest/load_table.py", "--table", "mmio_events", "--source", TARGET,
        "--output", f"{tables}/mmio_events_boot.parquet", jsonl, cwd=repo)
    facts = json.loads(run("uv", "run", "python", str(SOURCE / "query.py"), tables, cwd=repo))

    assert facts["functions"] == FUNCTIONS, facts["functions"]
    assert facts["calls"] == CALLS, facts["calls"]
    assert facts["strings"] == ["RIPCORD-FIXTURE\n"], facts["strings"]
    accesses = [x for x in facts["peripheral_xrefs"] if x[1] in ("READ", "WRITE")]
    assert accesses == PERIPHERAL_XREFS, facts["peripheral_xrefs"]
    assert facts["uart_tx"] == "RIPCORD-FIXTURE\n2437\n" and "RIPCORD-FIXTURE" in console
    assert facts["mmio_by_function"] == MMIO, facts["mmio_by_function"]
    total, to_functions = facts["recovered_calls"]
    assert to_functions == 2 and total > to_functions, facts["recovered_calls"]  # extra vector_table edges come from code bytes
    facts["recovered_calls"] = {"total": total, "to_known_functions": to_functions}
    facts["elf_sha256"] = run("shasum", "-a", "256", str(elf)).split()[0]
    facts["toolchain"] = {"clang": run("clang", "--version").splitlines()[0], "ld.lld": run("ld.lld", "--version").strip()}
    (build / "ripcord-results.json").write_text(json.dumps(facts, indent=2) + "\n")
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
