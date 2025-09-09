# network.py
from typing import Tuple, Dict, List, Optional
from shapely.geometry import Point
from osmnet.sensing_model import estimate_snr, check_los
from osmnet.buildings_loader import get_prepared_buildings
import random
import copy
from dataclasses import dataclass
from enum import Enum

# ==== Service Function Chain Components ====

class VNFType(Enum):
    """Types of Virtual Network Functions"""
    FIREWALL = "firewall"
    LOAD_BALANCER = "load_balancer"
    NAT = "nat"
    DPI = "dpi"  # Deep Packet Inspection
    CACHE = "cache"
    TRANSCODER = "transcoder"

@dataclass
class VNFRequirements:
    """Resource requirements for a VNF"""
    cpu: float  # CPU cores
    memory: float  # RAM in MB
    bandwidth: float  # Mbps
    latency_constraint: float  # max latency in ms

@dataclass
class VNF:
    """Virtual Network Function instance"""
    id: str
    vnf_type: VNFType
    requirements: VNFRequirements
    deployed_gnb: Optional[str] = None

@dataclass
class ServiceFunctionChain:
    """Ordered sequence of VNFs forming a service"""
    id: str
    vnfs: List[VNF]
    bandwidth_requirement: float  # end-to-end bandwidth
    latency_requirement: float    # end-to-end latency

@dataclass
class NetworkResources:
    """Available resources at a network node"""
    cpu: float
    memory: float
    bandwidth: float
    
    def can_accommodate(self, requirements: VNFRequirements) -> bool:
        return (self.cpu >= requirements.cpu and 
                self.memory >= requirements.memory and
                self.bandwidth >= requirements.bandwidth)
    
    def allocate(self, requirements: VNFRequirements):
        self.cpu -= requirements.cpu
        self.memory -= requirements.memory
        self.bandwidth -= requirements.bandwidth
    
    def deallocate(self, requirements: VNFRequirements):
        self.cpu += requirements.cpu
        self.memory += requirements.memory
        self.bandwidth += requirements.bandwidth

class GNBaseStation:
    """Represents a single gNB (base station) with SFCE capabilities."""
    def __init__(self, id: str, pos: Tuple[float, float], height: float, 
                 cpu: float = 10.0, memory: float = 1024.0, bandwidth: float = 1000.0):
        self.id = id
        self.pos = pos
        self.height = height
        self.connected_ues = set()
        
        # SFCE additions
        self.resources = NetworkResources(cpu, memory, bandwidth)
        self.deployed_vnfs: Dict[str, VNF] = {}
        self.active_sfcs: Dict[str, ServiceFunctionChain] = {}

class UE:
    """Represents a UE (vehicle or pedestrian)."""
    def __init__(self, id: str, height: float = 1.5):
        self.id = id
        self.height = height
        self.serving_gnb = None
        self.snr = None
        self.los = None

class NetworkEnvironment:
    """
    Tracks gNBs, UEs, and connectivity metrics.
    Provides SNR/LOS computation and best-cell association.
    """

    def __init__(self, gnb_configs: Dict, poi_file: str, buildings_3d=None):
        self.gnbs = {gid: GNBaseStation(gid, info['pos'], info['height'])
                     for gid, info in gnb_configs.items()}

        self.ues: Dict[str, UE] = {}
        self.poi_file = poi_file
        self.buildings_3d = buildings_3d
        if self.buildings_3d is None:
            # Load buildings independently to avoid circular import
            from sumolib import net as sumolib_net
            import os
            ROOT = os.path.dirname(os.path.dirname(__file__))
            NET_FILE = os.path.join(ROOT, "data", "map.net.xml")
            net = sumolib_net.readNet(NET_FILE)
            polys, _ = get_prepared_buildings(poi_file, net)
            from osmnet.sensing_model import assign_building_heights
            self.buildings_3d = assign_building_heights(polys)

    def register_ue(self, ue_id: str, height: float = 1.5):
        self.ues[ue_id] = UE(ue_id, height)

    def remove_ue(self, ue_id: str):
        if ue_id in self.ues:
            gnb_id = self.ues[ue_id].serving_gnb
            if gnb_id and ue_id in self.gnbs[gnb_id].connected_ues:
                self.gnbs[gnb_id].connected_ues.remove(ue_id)
            del self.ues[ue_id]

    def best_cell(self, ue_pos: Tuple[float, float]) -> Tuple[str, float, Dict[str, float]]:
        """Returns the best gNB for this position based on SNR."""
        scores = {}
        for gid, gnb in self.gnbs.items():
            snr, los, _, _ = estimate_snr(
                ue_pos, gnb.pos,
                ue_height=1.5,
                gn_height=gnb.height,
                buildings_3d=self.buildings_3d
            )
            scores[gid] = snr
        best = max(scores, key=scores.get)
        return best, scores[best], scores

    def update_ue_metrics(self, ue_id: str, ue_pos: Tuple[float, float]):
        """Update SNR, LOS, and serving gNB for a UE."""
        if ue_id not in self.ues:
            self.register_ue(ue_id)

        ue = self.ues[ue_id]
        best, snr, _ = self.best_cell(ue_pos)
        los = check_los(
            ue_pos, self.gnbs[best].pos,
            ue_height=ue.height,
            gn_height=self.gnbs[best].height,
            buildings_3d=self.buildings_3d
        )

        # Handle handover
        if ue.serving_gnb != best:
            if ue.serving_gnb:
                self.gnbs[ue.serving_gnb].connected_ues.discard(ue_id)
            self.gnbs[best].connected_ues.add(ue_id)
            ue.serving_gnb = best

        ue.snr = snr
        ue.los = los
        return best, snr, los

    def aggregate_metrics(self):
        """
        Returns a snapshot of environmental metrics usable by the SFCE agent:
        - UE positions
        - SNR per UE
        - LOS
        - Connected UE counts per gNB
        """
        snapshot = {
            'ues': {ue_id: {'snr': ue.snr, 'los': ue.los, 'serving_gnb': ue.serving_gnb}
                    for ue_id, ue in self.ues.items()},
            'gnbs': {gid: {'connected_ues': len(gnb.connected_ues)} for gid, gnb in self.gnbs.items()}
        }
        return snapshot
    
    def snapshot(self):
        """
        Returns a dict containing the current state of all UEs and gNBs.
        Example structure:
        {
            "ues": {
                "veh0": {"pos": (x,y), "snr": val, "los": bool, "gnb": "g0"},
                ...
            },
            "gnbs": {
                "g0": {"pos": (x,y), "height": h, "connected_ues": ["veh0", "ped1", ...]},
                ...
            }
        }
        """
        ue_state = {}
        gnb_state = {g: {"pos": info["pos"], "height": info["height"], "connected_ues": []}
                      for g, info in self.gnbs.items()}

        for ue_id, data in self.ues.items():
            ue_state[ue_id] = {
                "pos": data["pos"],
                "snr": data["snr"],
                "los": data["los"],
                "gnb": data["serving_gnb"]
            }
            gnb_state[data["serving_gnb"]]["connected_ues"].append(ue_id)

        return {"ues": ue_state, "gnbs": gnb_state}

    # ==== SFCE Management Methods ====
    
    def deploy_vnf(self, vnf: VNF, gnb_id: str) -> bool:
        """Deploy a VNF to a specific gNB if resources allow."""
        if gnb_id not in self.gnbs:
            return False
            
        gnb = self.gnbs[gnb_id]
        if not gnb.resources.can_accommodate(vnf.requirements):
            return False
            
        gnb.resources.allocate(vnf.requirements)
        gnb.deployed_vnfs[vnf.id] = vnf
        vnf.deployed_gnb = gnb_id
        return True
    
    def undeploy_vnf(self, vnf_id: str, gnb_id: str) -> bool:
        """Remove a VNF from a gNB and free resources."""
        if gnb_id not in self.gnbs or vnf_id not in self.gnbs[gnb_id].deployed_vnfs:
            return False
            
        gnb = self.gnbs[gnb_id]
        vnf = gnb.deployed_vnfs[vnf_id]
        gnb.resources.deallocate(vnf.requirements)
        del gnb.deployed_vnfs[vnf_id]
        vnf.deployed_gnb = None
        return True
    
    def deploy_sfc(self, sfc: ServiceFunctionChain) -> Dict[str, str]:
        """
        Deploy a Service Function Chain across gNBs using a simple greedy algorithm.
        Returns mapping of VNF ID to gNB ID, or empty dict if deployment failed.
        """
        deployment_plan = {}
        deployed_vnfs = []
        
        # Greedy deployment: try to place each VNF on the gNB with most available resources
        for vnf in sfc.vnfs:
            best_gnb = None
            best_score = -1
            
            for gnb_id, gnb in self.gnbs.items():
                if gnb.resources.can_accommodate(vnf.requirements):
                    # Score based on remaining resources after deployment
                    score = (gnb.resources.cpu - vnf.requirements.cpu + 
                            gnb.resources.memory - vnf.requirements.memory)
                    if score > best_score:
                        best_score = score
                        best_gnb = gnb_id
            
            if best_gnb is None:
                # Rollback previous deployments
                for deployed_vnf in deployed_vnfs:
                    self.undeploy_vnf(deployed_vnf.id, deployed_vnf.deployed_gnb)
                return {}
            
            if self.deploy_vnf(vnf, best_gnb):
                deployment_plan[vnf.id] = best_gnb
                deployed_vnfs.append(vnf)
            else:
                # Rollback
                for deployed_vnf in deployed_vnfs:
                    self.undeploy_vnf(deployed_vnf.id, deployed_vnf.deployed_gnb)
                return {}
        
        # Store active SFC
        for gnb_id in set(deployment_plan.values()):
            self.gnbs[gnb_id].active_sfcs[sfc.id] = sfc
            
        return deployment_plan
    
    def get_resource_utilization(self) -> Dict[str, Dict[str, float]]:
        """Get current resource utilization per gNB."""
        utilization = {}
        for gnb_id, gnb in self.gnbs.items():
            total_cpu = gnb.resources.cpu + sum(vnf.requirements.cpu for vnf in gnb.deployed_vnfs.values())
            total_memory = gnb.resources.memory + sum(vnf.requirements.memory for vnf in gnb.deployed_vnfs.values())
            total_bandwidth = gnb.resources.bandwidth + sum(vnf.requirements.bandwidth for vnf in gnb.deployed_vnfs.values())
            
            utilization[gnb_id] = {
                'cpu_used': sum(vnf.requirements.cpu for vnf in gnb.deployed_vnfs.values()),
                'cpu_total': total_cpu,
                'cpu_utilization': sum(vnf.requirements.cpu for vnf in gnb.deployed_vnfs.values()) / total_cpu if total_cpu > 0 else 0,
                'memory_used': sum(vnf.requirements.memory for vnf in gnb.deployed_vnfs.values()),
                'memory_total': total_memory,
                'memory_utilization': sum(vnf.requirements.memory for vnf in gnb.deployed_vnfs.values()) / total_memory if total_memory > 0 else 0,
                'bandwidth_used': sum(vnf.requirements.bandwidth for vnf in gnb.deployed_vnfs.values()),
                'bandwidth_total': total_bandwidth,
                'bandwidth_utilization': sum(vnf.requirements.bandwidth for vnf in gnb.deployed_vnfs.values()) / total_bandwidth if total_bandwidth > 0 else 0
            }
        return utilization