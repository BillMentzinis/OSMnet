# buildings_loader.py
from lxml import etree
from shapely.geometry import Point, Polygon
from shapely.prepared import prep
from typing import List, Tuple, Optional
from functools import lru_cache

def _polys_from_poi(poi_file: str) -> List[Polygon]:
    tree = etree.parse(poi_file)
    root = tree.getroot()
    buildings = []
    for poly in root.xpath('//poly[@type="building"]'):
        shape_str = poly.get('shape')
        if shape_str:
            coords = [tuple(map(float, c.split(','))) for c in shape_str.split()]
            buildings.append(Polygon(coords))
    return buildings

def _to_net_xy(polys: List[Polygon], net) -> List[Polygon]:
    # If POI already in net coords, no-op. If they’re lon/lat, convert here.
    # Heuristic: inspect a vertex range; if in [-180,180]x[-90,90], treat as lon/lat.
    def looks_geo(x, y): return -180 <= x <= 180 and -90 <= y <= 90
    sample_x, sample_y = polys[0].exterior.coords[0]
    as_geo = looks_geo(sample_x, sample_y)
    if not as_geo:
        return polys

    out = []
    for poly in polys:
        xy = [net.convertLonLat2XY(lon, lat) for lon, lat in poly.exterior.coords]
        out.append(Polygon(xy))
    return out

@lru_cache(maxsize=1)
def get_prepared_buildings(poi_file: str, net) -> Tuple[List[Polygon], List]:
    polys = _polys_from_poi(poi_file)
    polys = _to_net_xy(polys, net)
    # Prep for fast intersection tests
    prepped = [prep(p) for p in polys]
    return polys, prepped