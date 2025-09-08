# env_sfc.py
import gymnasium as gym
import numpy as np

class SFCEnv(gym.Env):
    def __init__(self, sim, substrate, k_cells=3, k_nodes=10):
        self.sim = sim              # your SUMO/Traci wrapper
        self.substrate = substrate  # your network graph (nodes, links, caps)
        self.k_cells = k_cells
        self.k_nodes = k_nodes

        # Observation: [UE x,y,v, best_snr, second_snr, los, cell_loads..., node_caps...]
        n_obs = 3 + 3 + k_cells + (3*k_nodes)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, shape=(n_obs,), dtype=np.float32)
        self.action_space = gym.spaces.MultiDiscrete([k_nodes]*3)  # e.g., place 3 VNFs

    def reset(self, *, seed=None, options=None):
        obs = self._observe()
        return obs, {}

    def step(self, action):
        # Apply placement decision (reserve caps, compute shortest path latency, etc.)
        cost, feasible = self._evaluate(action)
        # Advance mobility one tick
        self.sim.step()
        obs = self._observe()
        # Reward: negative latency, penalties for infeasible, plus sensing bonus
        reward = -cost - (0.0 if feasible else 100.0) + self._sensing_bonus()
        terminated = False
        truncated = False
        return obs, reward, terminated, truncated, {}

    def _observe(self):
        # pull last computed sensing + network state and flatten
        return np.asarray(self.sim.last_obs, dtype=np.float32)

    def _evaluate(self, action):
        # compute path, latency = prop + proc + queue + backhaul; check constraints
        return 10.0, True

    def _sensing_bonus(self):
        # reward LoS, high SNR, stable cell; penalize handovers during chain lifetime
        return 0.0