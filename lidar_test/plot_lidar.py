import pandas as pd
import matplotlib
matplotlib.use("Agg")  # use non-GUI backend
import matplotlib.pyplot as plt
import numpy as np
import glob

# Grab the latest lidar log file
file = sorted(glob.glob("lidar_log_*.csv"))[-1]
print(f"Plotting {file}...")

df = pd.read_csv(file)

angles = np.radians(df["angle_deg"].values)
distances = df["distance_mm"].values / 1000.0  # mm → m

x = np.sin(angles) * distances
y = np.cos(angles) * distances

plt.figure(figsize=(8,8))
plt.scatter(x, y, s=2, c=df["confidence"], cmap="plasma")
plt.axis("equal")
plt.xlabel("X (m)")
plt.ylabel("Y (m)")
plt.title("LD06 LiDAR Scan")
plt.tight_layout()
plt.savefig("scan.png", dpi=300)
print("Saved plot as scan.png")
