"""Re-run the network-delay analysis from the stored exports.
The analysis script injection/netdelay/analyze_netdelay.py is used unchanged. This wrapper only points it at the
repository folders: inputs from data/netdelay/, the released pipeline of this repository, outputs to OUT.
Usage (BARO environment of requirements.txt):
    python analysis/camera_ready/netdelay/reproduce_netdelay.py [OUT]
then compare OUT/RESULTS_NETDELAY_numbers.json with data/results/netdelay/RESULTS_NETDELAY_numbers.json."""
import importlib.util
import os
import sys
import tempfile

sys.dont_write_bytecode = True  # keep the script folder free of caches
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
spec = importlib.util.spec_from_file_location(
    "analyze_netdelay", os.path.join(REPO, "injection", "netdelay", "analyze_netdelay.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.HERE = os.path.join(REPO, "data", "netdelay")
m.REPO = REPO
m.OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="netdelay_")
print("output:", m.OUT)
m.main()
