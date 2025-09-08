# runner.py
import os
import sys
import random
import traci
from sumolib import net as sumolib_net
from sensing_model import estimate_snr, check_los, get_prepared_buildings, assign_building_heights
from features import FeatureLogger

# ==== CONFIG ====
SUMO_HOME = r"C:\Program Files (x86)\Eclipse\Sumo"
SUMO_BINARY = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")
SUMO_CONFIG = "map.sumocfg"
NET_FILE = "map.net.xml"
POI_FILE = "map.poi.xml"
MAX_STEPS = 200
NUM_VEHICLES = 5
NUM_PEDESTRIANS = 5
RANDOM_SEED = 42

# gNB locations
GNBs = {
    "g0": {"pos": (615, 305), "height": 25},
    "g1": {"pos": (250, 120), "height": 20},
    "g2": {"pos": (900, 520), "height": 30},
}

UE_HEIGHT = 1.5  # meters

# ==== SETUP ====
os.environ["SUMO_HOME"] = SUMO_HOME
sys.path.append(os.path.join(SUMO_HOME, "tools"))
random.seed(RANDOM_SEED)

# ==== Load network ====
net = sumolib_net.readNet(NET_FILE)
polys, _ = get_prepared_buildings(POI_FILE, net)
BUILDINGS_3D = assign_building_heights(polys)  # persistent random heights

drive_edges = [e.getID() for e in net.getEdges() if e.allows("passenger")]
walk_edges = [e.getID() for e in net.getEdges() if e.allows("pedestrian")]

print(f"drive_edges = {len(drive_edges)}")
print(f"walk_edges = {len(walk_edges)}")

# ==== Utility ====
def get_random_drive_edge():
    return random.choice(drive_edges)

def get_random_walk_edge():
    return random.choice(walk_edges)

# ==== Spawn functions ====
def assign_new_vehicle_trip(vehicle_id, initial=False):
    while True:
        from_edge = get_random_drive_edge()
        to_edge = get_random_drive_edge()
        if from_edge == to_edge:
            continue
        try:
            route = traci.simulation.findRoute(from_edge, to_edge).edges
            if not route:
                continue
            depart_time = 0 if initial else traci.simulation.getTime()
            traci.vehicle.add(vehicle_id, routeID="", depart=depart_time)
            traci.vehicle.setRoute(vehicle_id, route)
            return
        except traci.TraciException:
            continue

def assign_new_pedestrian_trip(ped_id, initial=False):
    while True:
        from_edge = get_random_walk_edge()
        to_edge = get_random_walk_edge()
        if from_edge == to_edge:
            continue
        try:
            route = traci.simulation.findRoute(
                from_edge, to_edge, vType="DEFAULT_PEDTYPE"
            ).edges
            if not route:
                continue
            depart_time = 0 if initial else traci.simulation.getTime()
            # Pedestrians as vehicles
            traci.vehicle.add(
                ped_id,
                routeID="",
                typeID="DEFAULT_PEDTYPE",
                depart=depart_time
            )
            traci.vehicle.setRoute(ped_id, route)
            return
        except traci.TraciException:
            continue

# ==== Best-cell function with 3D SNR ====
def best_cell(ue_pos):
    scores = {}
    for g, info in GNBs.items():
        gn_pos = info["pos"]
        gn_height = info["height"]
        snr, los, _, _ = estimate_snr(
            ue_pos, gn_pos,
            ue_height=UE_HEIGHT,
            gn_height=gn_height,
            buildings_3d=BUILDINGS_3D
        )
        scores[g] = snr
    best = max(scores, key=scores.get)
    return best, scores[best], scores

# ==== Main simulation ====
def main():
    traci.start([SUMO_BINARY, "-c", SUMO_CONFIG])
    step = 0
    feat = FeatureLogger("rollout.csv")

    # Spawn initial agents
    for i in range(NUM_VEHICLES):
        assign_new_vehicle_trip(f"veh{i}", initial=True)
        print(f"Created vehicle {i}")

    for i in range(NUM_PEDESTRIANS):
        assign_new_pedestrian_trip(f"ped{i}", initial=True)
        print(f"Created pedestrian {i}")

    while step < MAX_STEPS:
        traci.simulationStep()
        print(f"\n=== Step {step} ===")

        for vid in traci.vehicle.getIDList():
            pos = traci.vehicle.getPosition(vid)
            speed = traci.vehicle.getSpeed(vid)
            cell, snr, _ = best_cell(pos)
            los = check_los(
                pos, GNBs[cell]["pos"],
                ue_height=UE_HEIGHT,
                gn_height=GNBs[cell]["height"],
                buildings_3d=BUILDINGS_3D
            )

            agent_type = "ped" if vid.startswith("ped") else "veh"

            # Print live info
            print(f"[{agent_type.upper()}] {vid} | Pos={pos} | Speed={speed:.2f} | "
                  f"Cell={cell} | SNR={snr:.1f} dB | LOS={los}")

            # Log to CSV
            feat.log({
                "t": step,
                "agent_id": vid,
                "type": agent_type,
                "x": pos[0],
                "y": pos[1],
                "v": speed,
                "serving_cell": cell,
                "snr_dB": round(snr, 1),
                "los": int(los)
            })

            # Respawn if at end of route
            if traci.vehicle.getRouteIndex(vid) >= len(traci.vehicle.getRoute(vid)) - 1:
                traci.vehicle.remove(vid)
                if agent_type == "veh":
                    assign_new_vehicle_trip(vid)
                else:
                    assign_new_pedestrian_trip(vid)

        step += 1

    feat.close()
    traci.close()

if __name__ == "__main__":
    main()