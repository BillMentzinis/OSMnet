# OSMnetv2 - SUMO Network Simulation with 5G gNB Integration

A comprehensive SUMO-based traffic simulation platform that integrates 5G cellular network modeling, Service Function Chain Edge Computing (SFCE), and advanced sensing capabilities for urban mobility research.

## Overview

This project combines **SUMO (Simulation of Urban MObility)** with **5G network simulation** to create a realistic testbed for studying:

- Vehicle-to-Infrastructure (V2I) communications
- Pedestrian mobility patterns 
- 5G network performance in urban environments
- Service Function Chain (SFC) deployment at network edges
- Line-of-Sight (LOS) and Signal-to-Noise Ratio (SNR) modeling with 3D building awareness

## Key Features

### 🚗 Multi-Agent Simulation
- **Vehicle simulation**: Random trip generation with realistic routing
- **Pedestrian simulation**: Walkable network integration
- **Dynamic respawning**: Continuous agent flow throughout simulation

### 📡 5G Network Modeling
- **Multiple gNB stations**: Configurable base station locations and parameters
- **SNR calculation**: 3D-aware signal propagation modeling
- **LOS analysis**: Building-aware line-of-sight computation
- **Handover management**: Automatic best-cell association

### 🏢 3D Building Environment
- **Building height assignment**: Realistic 3D urban environment
- **Obstruction modeling**: Signal blockage by buildings
- **POI integration**: Point-of-interest data from OpenStreetMap

### ⚙️ Service Function Chain Edge Computing (SFCE)
- **VNF deployment**: Virtual Network Function placement on gNBs
- **Resource management**: CPU, memory, and bandwidth allocation
- **Service chaining**: End-to-end service deployment across edge nodes
- **Load balancing**: Intelligent VNF placement algorithms

### 📊 Comprehensive Logging
- **Mobility traces**: Agent positions, speeds, and trajectories  
- **Network metrics**: SNR, LOS, serving cell assignments
- **Resource utilization**: Edge computing resource consumption
- **Performance analysis**: CSV output for post-processing

## Project Structure

```
OSMnetv2/
├── osmnet/                    # Core simulation modules
│   ├── runner.py             # Main simulation entry point
│   ├── env.py                # Gymnasium environment wrapper
│   ├── network.py            # 5G network and SFCE management
│   ├── sensing_model.py      # SNR/LOS calculation algorithms
│   ├── buildings_loader.py   # 3D building data processing
│   ├── features.py           # Data logging utilities
│   ├── map_buildings.py      # Building visualization tools
│   └── env_sfc.py           # SFCE-specific environment
├── data/                      # Simulation input files
│   ├── map.net.xml           # SUMO network definition
│   ├── map.poi.xml           # Building/POI definitions
│   ├── map.sumocfg           # SUMO configuration
│   └── osmNetconvert*.typ.xml # Network type definitions
└── outputs/                   # Simulation results
    ├── rollout.csv           # Agent mobility traces
    ├── network_snapshots.csv # Network state snapshots  
    └── sfce_metrics.csv      # Edge computing metrics
```

## Core Components

### 1. Network Environment (`network.py`)
Manages the 5G cellular network infrastructure:

```python
# gNB configuration example
GNBs = {
    "g0": {"pos": (615, 305), "height": 25},
    "g1": {"pos": (250, 120), "height": 20}, 
    "g2": {"pos": (900, 520), "height": 30},
}
```

**Key Classes:**
- `NetworkEnvironment`: Main network controller
- `GNBaseStation`: Individual base station with SFCE capabilities
- `UE`: User equipment (vehicles/pedestrians)
- `ServiceFunctionChain`: Edge service definitions

### 2. Sensing Model (`sensing_model.py`)
Provides realistic 5G propagation modeling:

- **3D SNR calculation**: Considers building heights and antenna patterns
- **LOS detection**: Ray-tracing through 3D building models
- **Fresnel zone analysis**: Advanced propagation physics
- **Path loss modeling**: Free-space and non-line-of-sight scenarios

### 3. SFCE Framework (`network.py`)
Enables edge computing research:

**VNF Types:**
- Firewall, Load Balancer, NAT
- Deep Packet Inspection (DPI)
- Cache, Transcoder

**Resource Management:**
- CPU cores, RAM (MB), Bandwidth (Mbps)
- Latency constraints and QoS requirements
- Greedy placement algorithms

### 4. Gymnasium Integration (`env.py`)
Standard RL environment interface for:
- Multi-agent reinforcement learning
- Network optimization algorithms
- SFCE placement strategies

## Installation & Setup

### Prerequisites
- **Python 3.8+**
- **SUMO 1.18+** installed and configured
- Required Python packages:

```bash
pip install sumolib traci gymnasium numpy shapely lxml
```

### SUMO Installation
1. Download from [SUMO Official Website](https://www.eclipse.org/sumo/)
2. Set `SUMO_HOME` environment variable
3. Update `SUMO_HOME` path in `runner.py:16`

### Configuration
Edit key parameters in `runner.py`:

```python
# Simulation parameters  
MAX_STEPS = 200
NUM_VEHICLES = 5
NUM_PEDESTRIANS = 5
UE_HEIGHT = 1.5  # meters

# gNB configuration
GNBs = {
    "g0": {"pos": (615, 305), "height": 25},
    # Add more base stations...
}
```

## Usage

### Basic Simulation
```bash
cd OSMnetv2
python osmnet/runner.py
```

This will:
1. Start SUMO with GUI visualization
2. Spawn vehicles and pedestrians  
3. Run network simulation for `MAX_STEPS`
4. Generate output CSV files in `outputs/`

### Gymnasium Environment
```python
from osmnet.env import SUMONetworkEnv

env = SUMONetworkEnv(
    sumo_cfg="data/map.sumocfg",
    net_file="data/map.net.xml", 
    poi_file="data/map.poi.xml",
    gnb_configs=GNBs
)

obs = env.reset()
for step in range(100):
    action = env.action_space.sample()  # Random action
    obs, reward, done, truncated, info = env.step(action)
    if done:
        break
```

### SFCE Service Deployment
```python
from osmnet.network import VNF, VNFType, ServiceFunctionChain

# Create VNF
firewall = VNF(
    id="fw1",
    vnf_type=VNFType.FIREWALL,
    requirements=VNFRequirements(cpu=1.0, memory=128.0, bandwidth=50.0)
)

# Create service chain
sfc = ServiceFunctionChain(
    id="web_service",
    vnfs=[firewall],
    bandwidth_requirement=100.0,
    latency_requirement=10.0
)

# Deploy to network
deployment = net_env.deploy_sfc(sfc)
```

## Output Data

### 1. Mobility Traces (`rollout.csv`)
Agent movement and network associations:
```csv
t,agent_id,type,x,y,v,serving_cell,snr_dB,los
0,veh0,veh,245.8,112.3,8.5,g1,15.2,1
0,ped0,ped,620.1,308.7,1.2,g0,22.1,1
```

### 2. Network Snapshots (`network_snapshots.csv`) 
Network state per timestep:
```csv
t,ue_id,x,y,serving_gnb,snr_dB,los,gnb_connected_count
0,veh0,245.8,112.3,g1,15.2,1,3
```

### 3. SFCE Metrics (`sfce_metrics.csv`)
Edge computing resource utilization:
```csv
t,gnb_id,cpu_used,cpu_total,cpu_util,memory_used,memory_total,memory_util
0,g0,2.0,10.0,0.200,384.0,1024.0,0.375
```

## Research Applications

### Network Optimization
- **Coverage planning**: Optimal gNB placement
- **Handover algorithms**: Seamless connectivity  
- **Resource allocation**: Dynamic spectrum management

### Edge Computing
- **VNF placement**: Service chain optimization
- **Load balancing**: Distributed computing strategies
- **Latency minimization**: QoS-aware deployment

### Mobility Analysis  
- **V2I performance**: Vehicle connectivity patterns
- **Pedestrian behavior**: Urban mobility modeling
- **Mixed traffic**: Multi-modal transportation

## Advanced Features

### Custom Network Topologies
Replace `data/map.net.xml` with your own SUMO network:
```bash
netconvert --osm-files your_map.osm -o data/map.net.xml
polyconvert --osm-files your_map.osm --net-file data/map.net.xml -o data/map.poi.xml
```

### Building Data Integration
The system automatically processes OpenStreetMap building data:
- Polygon extraction from POI files
- 3D height assignment (random distribution)
- Coordinate system conversion

### Reinforcement Learning Integration
Use the Gymnasium environment for RL research:
```python
import gymnasium as gym
from stable_baselines3 import PPO

env = SUMONetworkEnv(...)
model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=10000)
```

## Configuration Files

### SUMO Configuration (`map.sumocfg`)
Standard SUMO configuration linking network and route files.

### Network Type Files (`osmNetconvert*.typ.xml`) 
Define road types, speeds, and pedestrian access permissions.

## Contributing

This project is designed for research and educational purposes. Key areas for contribution:

1. **Propagation Models**: Enhanced 5G channel modeling
2. **SFCE Algorithms**: Advanced VNF placement strategies  
3. **Visualization**: Real-time network performance dashboards
4. **Integration**: Support for other mobility simulators

## License

Open source research project. Please cite appropriately in academic work.

## Troubleshooting

### Common Issues

**SUMO not found**: 
- Verify SUMO installation and `SUMO_HOME` environment variable
- Update `SUMO_HOME` path in `runner.py`

**Missing Python packages**:
```bash
pip install sumolib traci gymnasium numpy shapely lxml
```

**No route found errors**:
- Ensure network topology allows routing between random edges
- Check vehicle type definitions and edge permissions

**Building data not loading**:
- Verify POI file format and building polygon definitions
- Check coordinate system consistency between network and POI files

### Performance Tips

- **Reduce agent count** for faster simulation
- **Disable SUMO GUI** for headless execution  
- **Limit simulation steps** for initial testing
- **Profile memory usage** for large networks

---

**Project Status**: Active development on `network-dev` branch
**SUMO Version**: Tested with SUMO 1.18+  
**Python Version**: 3.8+

For questions and issues, please refer to the project documentation or create an issue in the repository.