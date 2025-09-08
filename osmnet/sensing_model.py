# sensing_model.py
from shapely.geometry import LineString
# from osmnet.buildings_loader import get_prepared_buildings
import math
import random

POI_FILE = "map.poi.xml"

DEFAULT_B_H = 15.0  # m, fallback building height
H_UE = 1.5
H_GNB = 20.0

def _first_fresnel_radius(d1, d2, f_hz):
    lam = 3e8 / f_hz
    return math.sqrt(lam * d1 * d2 / (d1 + d2))

# ---- Building heights ----
def assign_building_heights(buildings, min_height=10, max_height=50):
    """
    Returns a list of tuples (Polygon, height) with persistent random heights
    """
    return [(b, random.uniform(min_height, max_height)) for b in buildings]

# ---- 3D LOS check ----
def check_los_3d(ue_pos, ue_height, gn_pos, gn_height, buildings_with_heights):
    """
    buildings_with_heights: list of (Polygon, height)
    """
    line_2d = LineString([ue_pos, gn_pos])
    for poly, h in buildings_with_heights:
        if line_2d.intersects(poly):
            mid_x = (ue_pos[0] + gn_pos[0]) / 2
            mid_y = (ue_pos[1] + gn_pos[1]) / 2
            d_total = math.dist(ue_pos, gn_pos)
            d_mid = math.dist(ue_pos, (mid_x, mid_y))
            los_height_at_mid = ue_height + (gn_height - ue_height) * (d_mid / d_total)
            if h > los_height_at_mid:
                return False
    return True

# ---- 3D-aware SNR estimation ----
def estimate_snr_3d(ue_pos, gn_pos, ue_height=H_UE, gn_height=H_GNB,
                    freq_hz=2.4e9, Pt_dBm=20, noise_floor_dBm=-100,
                    buildings_3d=None):
    """
    Estimates SNR considering 3D building heights
    """
    if buildings_3d is None:
        raise ValueError("buildings_3d must be provided")

    los = check_los_3d(ue_pos, ue_height, gn_pos, gn_height, buildings_3d)

    d = max(1.0, math.dist(ue_pos, gn_pos))
    fspl = 20 * math.log10(d) + 20 * math.log10(freq_hz) - 147.55
    Pr_dBm = Pt_dBm - fspl
    if not los:
        Pr_dBm -= 20  # NLOS penalty

    snr = Pr_dBm - noise_floor_dBm
    return snr, los, Pr_dBm, fspl

# ---- Wrapper functions ----
def check_los(ue_xy, gnb_xy, ue_height=H_UE, gn_height=H_GNB, buildings_3d=None):
    return check_los_3d(ue_xy, ue_height, gnb_xy, gn_height, buildings_3d)

def estimate_snr(ue_xy, gnb_xy, ue_height=H_UE, gn_height=H_GNB,
                 buildings_3d=None, f_hz=3.5e9, tx_dBm=30.0,
                 bw_hz=20e6, noise_fig_dB=7.0, g_tx_dBi=8.0,
                 g_rx_dBi=0.0, nlos_penalty_dB=20.0):
    snr, los, pr_dBm, fspl = estimate_snr_3d(
        ue_xy, gnb_xy,
        ue_height=ue_height,
        gn_height=gn_height,
        freq_hz=f_hz,
        Pt_dBm=tx_dBm,
        noise_floor_dBm=-174 + 10 * math.log10(bw_hz) + noise_fig_dB,
        buildings_3d=buildings_3d
    )
    # Apply antenna gains
    snr += g_tx_dBi + g_rx_dBi
    # Apply extra NLOS penalty if needed
    if not los:
        snr -= nlos_penalty_dB

    return snr, los, pr_dBm, fspl