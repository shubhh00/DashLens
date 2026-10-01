"""Fill server/cache/ with the cars most likely to be asked about, one at a time.

Run from server/:
    .venv\\Scripts\\python.exe app\\manual\\prewarm.py
Already-cached cars are skipped, so it is safe to re-run after a Gemini quota reset.
"""
from __future__ import annotations

import sys
import time

from manual_pipeline import find_cached, lookup_manual

# India's highest-volume models first, so a quota cut-off still leaves the common cars covered.
CARS = [
    ("Maruti", "Swift"), ("Maruti", "Baleno"), ("Maruti", "Brezza"), ("Maruti", "Dzire"),
    ("Maruti", "Ertiga"), ("Maruti", "WagonR"), ("Maruti", "Fronx"), ("Hyundai", "Creta"),
    ("Tata", "Nexon"), ("Tata", "Punch"), ("Mahindra", "Scorpio"), ("Hyundai", "Venue"),
    ("Maruti", "Grand Vitara"), ("Kia", "Seltos"), ("Kia", "Sonet"), ("Hyundai", "i20"),
    ("Tata", "Tiago"), ("Maruti", "Alto K10"), ("Mahindra", "XUV700"), ("Mahindra", "Thar"),
    ("Hyundai", "Exter"), ("Toyota", "Innova"), ("Hyundai", "Verna"), ("Honda", "City"),
    ("Tata", "Altroz"), ("Mahindra", "XUV 3XO"), ("MG", "Astor"), ("MG", "Hector"),
    ("Tata", "Harrier"), ("Maruti", "Celerio"),
]


def main() -> None:
    done, failed = [], []
    for make, model in CARS:
        cached = find_cached(make, model)
        if cached and cached.get("structured", True):
            continue
        start = time.time()
        result = lookup_manual(make, model)
        took = f"{time.time() - start:.0f}s"
        if result.get("source") == "manual":
            done.append(f"{make} {model} ({len(result.get('lamps') or [])} lamps{'' if result.get('structured', True) else ', text only'}, {took})")
        else:
            failed.append(f"{make} {model} ({took})")
        print(f"[prewarm] {make} {model}: {result.get('source')} in {took}", flush=True)
    print("[prewarm] cached:", done or "none", flush=True)
    print("[prewarm] failed:", failed or "none", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
