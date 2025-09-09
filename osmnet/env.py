# osmnet/env.py
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import traci
from sumolib import net as sumolib_net
from osmnet.sensing_model import estimate_snr, check_los, assign_building_heights
from osmnet.buildings_loader import get_prepared_buildings
from osmnet.network import NetworkEnvironment

class SUMONetworkEnv(gym.Env):
    """
    Gymnasium environment wrapping SUMO + gNB network simulation.
    Each step updates vehicle/pedestrian positions and network metrics.
    Actions: agent can make VNF placement / service function decisions per gNB.
    Observations: positions, SNR, LOS, gNB load, etc.
    """
    metadata = {"render_modes": ["human"], "render_fps": 10}

    def __init__(self, sumo_cfg, net_file, poi_file, gnb_configs,
                 max_steps=200, num_vehicles=5, num_pedestrians=5,
                 ue_height=1.5):
        super().__init__()

        self.sumo_cfg = sumo_cfg
        self.net_file = net_file
        self.poi_file = poi_file
        self.gnb_configs = gnb_configs
        self.max_steps = max_steps
        self.num_vehicles = num_vehicles
        self.num_pedestrians = num_pedestrians
        self.UE_HEIGHT = ue_height

        # Load SUMO network
        self.net = sumolib_net.readNet(self.net_file)
        polys, _ = get_prepared_buildings(self.poi_file, self.net)
        self.BUILDINGS_3D = assign_building_heights(polys)

        self.drive_edges = [e.getID() for e in self.net.getEdges() if e.allows("passenger")]
        self.walk_edges = [e.getID() for e in self.net.getEdges() if e.allows("pedestrian")]

        # Network environment (metrics)
        self.net_env = NetworkEnvironment(
            gnb_configs=self.gnb_configs,
            poi_file=self.poi_file
        )

        # Observation space: [x, y, SNR, LOS, gNB load] for each UE
        obs_low = np.array([0, 0, -100, 0, 0]*self.num_vehicles, dtype=np.float32)
        obs_high = np.array([1000, 1000, 100, 1, self.num_vehicles]*self.num_vehicles, dtype=np.float32)
        self.observation_space = spaces.Box(low=obs_low, high=obs_high, dtype=np.float32)

        # Action space: Example: choose a gNB to place a VNF (0..num_gnbs-1)
        self.action_space = spaces.Discrete(len(self.gnb_configs))

        self.step_count = 0

    def reset(self, seed=None, options=None):
        # Start SUMO
        traci.start(["sumo-gui", "-c", self.sumo_cfg])
        self.step_count = 0

        # Spawn vehicles/pedestrians
        for i in range(self.num_vehicles):
            self._spawn_vehicle(f"veh{i}")
        for i in range(self.num_pedestrians):
            self._spawn_pedestrian(f"ped{i}")

        return self._get_obs(), {}

    def _spawn_vehicle(self, vid):
        from_edge = np.random.choice(self.drive_edges)
        to_edge = np.random.choice(self.drive_edges)
        while from_edge == to_edge:
            to_edge = np.random.choice(self.drive_edges)
        route = traci.simulation.findRoute(from_edge, to_edge).edges
        traci.vehicle.add(vid, routeID="", depart=0)
        traci.vehicle.setRoute(vid, route)
        self.net_env.register_ue(vid)

    def _spawn_pedestrian(self, pid):
        from_edge = np.random.choice(self.walk_edges)
        to_edge = np.random.choice(self.walk_edges)
        while from_edge == to_edge:
            to_edge = np.random.choice(self.walk_edges)
        route = traci.simulation.findRoute(from_edge, to_edge, vType="DEFAULT_PEDTYPE").edges
        traci.vehicle.add(pid, routeID="", typeID="DEFAULT_PEDTYPE", depart=0)
        traci.vehicle.setRoute(pid, route)
        self.net_env.register_ue(pid)

    def step(self, action):
        """
        action: integer representing gNB or other high-level network decision.
        """
        traci.simulationStep()
        self.step_count += 1

        ue_positions = {vid: traci.vehicle.getPosition(vid) for vid in traci.vehicle.getIDList()}
        obs = []

        # Update network metrics
        for vid, pos in ue_positions.items():
            serving_gnb, snr, los = self.net_env.update_ue_metrics(vid, pos)
            gnb_load = len([v for v in ue_positions if self.net_env.update_ue_metrics(v, ue_positions[v])[0]==serving_gnb])
            obs.extend([pos[0], pos[1], snr, float(los), gnb_load])

            # Respawn if at end
            if traci.vehicle.getRouteIndex(vid) >= len(traci.vehicle.getRoute(vid)) - 1:
                traci.vehicle.remove(vid)
                if vid.startswith("veh"):
                    self._spawn_vehicle(vid)
                else:
                    self._spawn_pedestrian(vid)

        obs = np.array(obs, dtype=np.float32)

        # Example reward: maximize SNR to the serving gNB
        reward = sum([self.net_env.update_ue_metrics(vid, ue_positions[vid])[1] for vid in ue_positions]) / len(ue_positions)

        done = self.step_count >= self.max_steps
        info = {}

        return obs, reward, done, False, info

    def render(self):
        # Optional: could integrate SUMO GUI metrics visualization
        pass

    def close(self):
        traci.close()