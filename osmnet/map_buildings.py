from shapely.geometry import Polygon # type: ignore
import osmnx as ox

gdf = ox.geometries_from_xml("map.osm", tags={"building": True})
BUILDINGS = gdf['geometry'].tolist()  # list of shapely polygons


# # Example rectangular buildings (can be adjusted for your map scale)
# BUILDINGS = [
#     Polygon([(50, 50), (70, 50), (70, 80), (50, 80)]),
#     Polygon([(150, 100), (180, 100), (180, 130), (150, 130)]),
#     Polygon([(200, 200), (230, 200), (230, 240), (200, 240)])
# ]

def get_buildings():
    return BUILDINGS
