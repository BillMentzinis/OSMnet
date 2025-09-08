# features.py
import csv, os

FIELDS = [
    "t", "agent_id", "type", "x", "y", "v", 
    "serving_cell", "snr_dB", "los",
    # optional: second_best_snr, cell_margin, area_density, blockage_ratio ...
]

class FeatureLogger:
    def __init__(self, path="rollout.csv"):
        self.path = path
        first = not os.path.exists(path)
        self.f = open(path, "a", newline="")
        self.w = csv.DictWriter(self.f, fieldnames=FIELDS)
        if first: self.w.writeheader()

    def log(self, row: dict):
        self.w.writerow(row)

    def close(self):
        self.f.close()