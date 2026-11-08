"""Sionna RT trial (ADR-0016): per-tower blockage and excess delay along one campus route.

A stretch experiment, kept out of CI and out of the normal install. In its own environment:
    python -m venv .sionna && .sionna/bin/pip install sionna-rt
    curl --data-urlencode "data@query" https://overpass-api.de/api/interpreter -o osm.json
with the query: [out:json];(way["building"](around:1800,45.3876,-75.6960););out tags geom;
    .sionna/bin/python analysis/sionna_campus.py osm.json <work folder>

Buildings are OpenStreetMap footprints (ODbL) extruded to OSM's height, or to DEFAULT_LEVELS when
it is missing. Walls only: a ray blocked by a building always crosses a wall. Trees are not
modelled and materials are assumed, so the table shapes the statistical model and its numbers
are not accuracy results unless checked against measurements (ADR-0015).
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ORIGIN = (45.3876, -75.6960, 70.0)
ROOT = Path(__file__).parents[1]
TOWERS = ROOT / "data" / "reference" / "cells-ottawa.csv"
OUT = ROOT / "data" / "reference" / "sionna-campus-route.csv"
CARRIER, TX_MHZ, MIN_KM, COUNT = "TELUS", 886.25, 0.8, 6  # the ottawa-towers scenario
RADIUS_M, SPEED_MPS, ALTITUDE_M, DURATION_S, STEP_S = 150.0, 8.0, 30.0, 360.0, 5.0
LEVEL_M, DEFAULT_LEVELS = 3.0, 3  # TBC: most OSM buildings here have no height
EPS_CONCRETE, SIGMA_CONCRETE = 5.24, 0.042  # ITU-R P.2040 concrete, extended below 1 GHz: TBC
EPS_GROUND, SIGMA_GROUND = 15.0, 0.035  # medium-dry ground: TBC
GROUND_ELEVATION_CUTOFF_M = 80.0
C = 299_792_458.0
_M_PER_DEG_LAT = 111_132.0
_M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(ORIGIN[0]))


def enu(lat, lon):
    return (lon - ORIGIN[1]) * _M_PER_DEG_LON, (lat - ORIGIN[0]) * _M_PER_DEG_LAT


def antenna_height(filed_m):
    """Height above local ground. The registry often omits ground elevation, so low filed values
    are taken as the antenna height alone (TBC)."""
    return filed_m if filed_m < GROUND_ELEVATION_CUTOFF_M else filed_m - ORIGIN[2]


def towers():
    rows = [
        r
        for r in csv.DictReader(open(TOWERS, newline=""))
        if CARRIER in r["carrier"]
        and float(r["tx_mhz"]) == TX_MHZ
        and float(r["dist_km"]) >= MIN_KM
    ]
    sites = {}
    for r in sorted(rows, key=lambda r: float(r["dist_km"])):
        sites.setdefault((r["lat"], r["lon"]), r)
    chosen = list(sites.values())[:COUNT]
    return [
        [*enu(float(r["lat"]), float(r["lon"])), antenna_height(float(r["height_m"]))]
        for r in chosen
    ]


def building_height(tags):
    if "height" in tags:
        try:
            return float(tags["height"].split()[0])
        except ValueError:
            pass
    try:
        return float(tags.get("building:levels", DEFAULT_LEVELS)) * LEVEL_M
    except ValueError:
        return DEFAULT_LEVELS * LEVEL_M


def write_ply(path, vertices, faces):
    with open(path, "w") as f:
        f.write(
            f"ply\nformat ascii 1.0\nelement vertex {len(vertices)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n"
        )
        f.writelines(f"{x:.2f} {y:.2f} {z:.2f}\n" for x, y, z in vertices)
        f.writelines(f"3 {a} {b} {c}\n" for a, b, c in faces)


def build_scene(osm_path, folder):
    vertices, faces = [], []
    for element in json.load(open(osm_path))["elements"]:
        points = [enu(p["lat"], p["lon"]) for p in element.get("geometry", [])]
        top = building_height(element.get("tags", {}))
        for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
            i = len(vertices)
            vertices += [(x0, y0, 0.0), (x1, y1, 0.0), (x1, y1, top), (x0, y0, top)]
            faces += [(i, i + 1, i + 2), (i, i + 2, i + 3)]
    folder = Path(folder)
    write_ply(folder / "buildings.ply", vertices, faces)
    s = 6000.0
    write_ply(
        folder / "ground.ply",
        [(-s, -s, 0.0), (s, -s, 0.0), (s, s, 0.0), (-s, s, 0.0)],
        [(0, 1, 2), (0, 2, 3)],
    )
    xml = f"""<scene version="2.1.0">
  <bsdf type="radio-material" id="wall_material">
    <float name="relative_permittivity" value="{EPS_CONCRETE}"/>
    <float name="conductivity" value="{SIGMA_CONCRETE}"/>
  </bsdf>
  <bsdf type="radio-material" id="soil_material">
    <float name="relative_permittivity" value="{EPS_GROUND}"/>
    <float name="conductivity" value="{SIGMA_GROUND}"/>
  </bsdf>
  <shape type="ply" id="buildings">
    <string name="filename" value="buildings.ply"/>
    <ref id="wall_material"/>
  </shape>
  <shape type="ply" id="terrain">
    <string name="filename" value="ground.ply"/>
    <ref id="soil_material"/>
  </shape>
</scene>
"""
    (folder / "scene.xml").write_text(xml)
    return folder / "scene.xml", len(faces)


def main(osm_path, folder):
    import sionna.rt as rt

    scene_file, triangles = build_scene(osm_path, folder)
    print("triangles", triangles, flush=True)
    scene = rt.load_scene(str(scene_file))
    scene.frequency = TX_MHZ * 1e6
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = scene.tx_array
    emitters = towers()
    for i, e in enumerate(emitters):
        scene.add(rt.Transmitter(f"t{i}", position=e))
    times = np.arange(0.0, DURATION_S, STEP_S)
    angle = SPEED_MPS / RADIUS_M * times
    route = np.column_stack(
        [RADIUS_M * np.cos(angle), RADIUS_M * np.sin(angle), np.full_like(times, ALTITUDE_M)]
    )
    for k, p in enumerate(route):
        scene.add(rt.Receiver(f"r{k}", position=[float(x) for x in p]))
    print("solving", len(route), "points", len(emitters), "towers", flush=True)
    paths = rt.PathSolver()(
        scene,
        max_depth=2,
        los=True,
        specular_reflection=True,
        diffuse_reflection=False,
        refraction=False,
        diffraction=True,
        edge_diffraction=True,
        synthetic_array=True,
        samples_per_src=200_000,
        max_num_paths_per_src=200_000,
    )
    tau = paths.tau.numpy()
    a_re, a_im = (np.array(x) for x in paths.a)
    valid = np.array(paths.valid)
    print("shapes", tau.shape, a_re.shape, valid.shape, flush=True)
    interactions = np.array(paths.interactions)
    gains = np.squeeze(a_re**2 + a_im**2)
    rows = []
    for k, t in enumerate(times):
        for i, e in enumerate(emitters):
            ok = valid[k, i, :]
            geometric = float(np.linalg.norm(route[k] - np.array(e)))
            if not ok.any():
                rows.append([t, i, 0, "", ""])
                continue
            delays = tau[k, i, :][ok]
            power = float(gains[k, i, :][ok].sum())
            depth0 = interactions[0, k, i, :][ok] == 0
            rows.append(
                [
                    t,
                    i,
                    int(depth0.any()),
                    f"{max(delays.min() * C - geometric, 0.0):.2f}",
                    f"{10 * np.log10(power):.1f}",
                ]
            )
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "tower", "los", "excess_m", "gain_db"])
        w.writerows(rows)
    print("wrote", OUT, len(rows), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
