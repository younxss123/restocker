"""Temporary: run the real PlayStation Direct check every 10s for ~4 minutes from a runner."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import monitor
for i in range(24):
    t = time.time()
    print(i, monitor.psdirect_fetch(), f"{time.time() - t:.1f}s", flush=True)
    time.sleep(10)
