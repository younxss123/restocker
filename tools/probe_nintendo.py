"""Temporary: run the real Nintendo check every ~10s for 3 minutes from a GitHub runner."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import monitor
end = time.time() + 180
counts = {}
while time.time() < end:
    t = time.time()
    st, detail = monitor.nintendo_fetch()
    counts[st] = counts.get(st, 0) + 1
    print(f"{time.strftime('%H:%M:%S')} {time.time()-t:.2f}s {st}: {detail}", flush=True)
    time.sleep(max(0, 10 - (time.time() - t)))
print("totals:", counts)
