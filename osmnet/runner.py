# runner.py
import os
import sys
import random
import traci
from sumolib import net as sumolib_net
# from sensing_model import estimate_snr, check_los, get_prepared_buildings, assign_building_heights
from osmnet.sensing_model import estimate_snr, check_los, assign_building_heights
from osmnet.buildings_loader import get_prepared_buildings
from osmnet.features import FeatureLogger
from osmnet.network import NetworkEnvironment

# ==== CONFIG ====
ROOT = os.path.dirname(os.path.dirname(__file__))  # project root
DATA_DIR = os.path.join(ROOT, "data")
SUMO_HOME = r"C:\Program Files (x86)\Eclipse\Sumo"
SUMO_BINARY = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")
NET_FILE = os.path.join(DATA_DIR, "map.net.xml")
POI_FILE = os.path.join(DATA_DIR, "map.poi.xml")
SUMO_CONFIG = os.path.join(DATA_DIR, "map.sumocfg")
MAX_STEPS = 200
NUM_VEHICLES = 5
NUM_PEDESTRIANS = 5
RANDOM_SEED = 42

# output folder
OUTPUTS_DIR = os.path.join(ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
ROLLOUT_FILE = os.path.join(OUTPUTS_DIR, "rollout.csv")

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

# ==== Load SUMO network ====
net = sumolib_net.readNet(NET_FILE)
polys, _ = get_prepared_buildings(POI_FILE, net)
# Prepare building heights once and reuse
BUILDINGS_3D = assign_building_heights(polys)

drive_edges = [e.getID() for e in net.getEdges() if e.allows("passenger")]
walk_edges = [e.getID() for e in net.getEdges() if e.allows("pedestrian")]

print(f"drive_edges = {len(drive_edges)}")
print(f"walk_edges = {len(walk_edges)}")

# ==== Setup network environment with SFCE capabilities ====
net_env = NetworkEnvironment(
    gnb_configs=GNBs,
    poi_file=POI_FILE
)

# ==== SFCE Demo: Create sample service chains ====
from osmnet.network import VNF, VNFType, VNFRequirements, ServiceFunctionChain

def create_sample_sfcs():
    """Create sample Service Function Chains for demo."""
    # Web service chain
    vnf_firewall = VNF(
        id="fw_web",
        vnf_type=VNFType.FIREWALL,
        requirements=VNFRequirements(cpu=1.0, memory=128.0, bandwidth=50.0, latency_constraint=10.0)
    )
    vnf_lb = VNF(
        id="lb_web", 
        vnf_type=VNFType.LOAD_BALANCER,
        requirements=VNFRequirements(cpu=2.0, memory=256.0, bandwidth=100.0, latency_constraint=5.0)
    )
    
    web_sfc = ServiceFunctionChain(
        id="web_service",
        vnfs=[vnf_firewall, vnf_lb],
        bandwidth_requirement=150.0,
        latency_requirement=15.0
    )
    
    # Video service chain  
    vnf_transcoder = VNF(
        id="trans_video",
        vnf_type=VNFType.TRANSCODER,
        requirements=VNFRequirements(cpu=3.0, memory=512.0, bandwidth=200.0, latency_constraint=20.0)
    )
    vnf_cache = VNF(
        id="cache_video",
        vnf_type=VNFType.CACHE,
        requirements=VNFRequirements(cpu=1.0, memory=1024.0, bandwidth=300.0, latency_constraint=5.0)
    )
    
    video_sfc = ServiceFunctionChain(
        id="video_service",
        vnfs=[vnf_transcoder, vnf_cache],
        bandwidth_requirement=400.0,
        latency_requirement=25.0
    )
    
    return [web_sfc, video_sfc]

# Deploy sample SFCs
sample_sfcs = create_sample_sfcs()
print("=== SFCE Initialization ===")
for sfc in sample_sfcs:
    deployment = net_env.deploy_sfc(sfc)
    if deployment:
        print(f"[OK] {sfc.id} deployed: {deployment}")
    else:
        print(f"[FAIL] {sfc.id} deployment failed")

print(f"\nInitial resource utilization:")
utilization = net_env.get_resource_utilization()
for gnb_id, metrics in utilization.items():
    print(f"  {gnb_id}: CPU={metrics['cpu_utilization']:.1%}, "
          f"Memory={metrics['memory_utilization']:.1%}, "
          f"BW={metrics['bandwidth_utilization']:.1%}")

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
    feat = FeatureLogger(ROLLOUT_FILE)

    NETWORK_SNAPSHOT_FILE = os.path.join(OUTPUTS_DIR, "network_snapshots.csv")
    SFCE_METRICS_FILE = os.path.join(OUTPUTS_DIR, "sfce_metrics.csv")
    
    # open snapshot CSV
    with open(NETWORK_SNAPSHOT_FILE, "w") as net_log, open(SFCE_METRICS_FILE, "w") as sfce_log:
        # write headers
        net_log.write("t,ue_id,x,y,serving_gnb,snr_dB,los,gnb_connected_count\n")
        sfce_log.write("t,gnb_id,cpu_used,cpu_total,cpu_util,memory_used,memory_total,memory_util,bw_used,bw_total,bw_util,deployed_vnfs,active_sfcs\n")

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

            # Compute best cells for all UEs once
            ue_positions = {vid: traci.vehicle.getPosition(vid) for vid in traci.vehicle.getIDList()}
            ue_best_cells = {vid: best_cell(pos)[0] for vid, pos in ue_positions.items()}

            # Count connected UEs per gNB
            gnb_connected_counts = {g: 0 for g in GNBs}
            for cell in ue_best_cells.values():
                gnb_connected_counts[cell] += 1

            # Now loop through UEs
            for vid, pos in ue_positions.items():
                speed = traci.vehicle.getSpeed(vid)
                cell = ue_best_cells[vid]
                snr, los, _, _ = estimate_snr(
                    pos, GNBs[cell]["pos"],
                    ue_height=UE_HEIGHT,
                    gn_height=GNBs[cell]["height"],
                    buildings_3d=BUILDINGS_3D
                )

                agent_type = "ped" if vid.startswith("ped") else "veh"

                print(f"[{agent_type.upper()}] {vid} | Pos={pos} | Speed={speed:.2f} | "
                      f"Cell={cell} | SNR={snr:.1f} dB | LOS={los}")

                # Log to main rollout CSV
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

                # Log to network snapshot CSV
                connected_count = gnb_connected_counts[cell]
                net_log.write(f"{step},{vid},{pos[0]},{pos[1]},{cell},{round(snr,1)},{int(los)},{connected_count}\n")

            # Log SFCE metrics every step
            utilization = net_env.get_resource_utilization()
            for gnb_id, metrics in utilization.items():
                vnf_count = len(net_env.gnbs[gnb_id].deployed_vnfs)
                sfc_count = len(net_env.gnbs[gnb_id].active_sfcs)
                sfce_log.write(f"{step},{gnb_id},{metrics['cpu_used']},{metrics['cpu_total']},{metrics['cpu_utilization']:.3f},"
                              f"{metrics['memory_used']},{metrics['memory_total']},{metrics['memory_utilization']:.3f},"
                              f"{metrics['bandwidth_used']},{metrics['bandwidth_total']},{metrics['bandwidth_utilization']:.3f},"
                              f"{vnf_count},{sfc_count}\n")

                # Respawn at end of route
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