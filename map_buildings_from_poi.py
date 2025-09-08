from lxml import etree
from shapely.geometry import Point, Polygon, LineString
from pyproj import Transformer

# Setup CRS transformer (adjust EPSG codes as needed)
transformer = Transformer.from_crs("epsg:4326", "epsg:32633", always_xy=True)

def load_pois_and_buildings(poi_file):
    tree = etree.parse(poi_file)
    root = tree.getroot()

    pois = []
    buildings = []

    # Extract POIs (points) with x,y attributes
    for poi in root.xpath('//poi'):
        x = poi.get('x')
        y = poi.get('y')
        if x is not None and y is not None:
            pois.append(Point(float(x), float(y)))

    # Extract building polygons
    for poly in root.xpath('//poly[@type="building"]'):
        shape_str = poly.get('shape')
        if shape_str:
            coords = [tuple(map(float, c.split(','))) for c in shape_str.split()]
            buildings.append(Polygon(coords))

    return pois, buildings

# def transform_geometry(geom, transformer):
#     if geom.geom_type == 'Point':
#         x, y = transformer.transform(geom.x, geom.y)
#         return Point(x, y)
#     elif geom.geom_type == 'Polygon':
#         coords = [transformer.transform(x, y) for x, y in geom.exterior.coords]
#         return Polygon(coords)
#     else:
#         return geom

def check_building_intersection(building, network):
    for edge in network.getEdges():
        edge_shape = LineString(edge.getShape())
        if building.intersects(edge_shape):
            return True
    return False

def get_buildings(poi_file):
    pois, buildings = load_pois_and_buildings(poi_file)

    # # Transform geometries to match SUMO network CRS
    # pois = [transform_geometry(p, transformer) for p in pois]
    # buildings = [transform_geometry(b, transformer) for b in buildings]

    return buildings

# def main(poi_file, net_file):
#     pois, buildings = load_pois_and_buildings(poi_file)

#     # Transform geometries to match SUMO network CRS
#     pois = [transform_geometry(p, transformer) for p in pois]
#     buildings = [transform_geometry(b, transformer) for b in buildings]

    # # Load SUMO network
    # network = net.readNet(net_file)

    # # Check each building for intersection with network
    # for i, building in enumerate(buildings):
    #     if check_building_intersection(building, network):
    #         print(f"Building {i} intersects with the network.")
    #     else:
    #         print(f"Building {i} does not intersect with the network.")

# # Example usage:
# main("map.poi.xml", "map.net.xml")