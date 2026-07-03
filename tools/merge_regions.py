"""Merge per-region decomp output into versioned info files.

decomp.py produces a single-region symbol map (plain integer addresses) for
one ELF. This script combines one or more of those per-region maps into the
final yaml/<game> info files, versioning addr/size by region ({J: .., U: ..})
whenever they differ or a symbol only exists in some regions.

It also carries over enrichment (type, count, params, return and manually
edited desc) from an existing info directory, matched by label, so type/param
information generated previously is not lost when the map is regenerated.

Usage:
  merge_regions.py --game fe8 --dst ../yaml/fe8 [--carryover ../yaml/fe8] \
      --region U:/tmp/fe8u_out --region J:/tmp/fe8j_out
"""
import argparse
import os
from functools import cmp_to_key
from constants import MAP_CODE, MAP_DATA, MAP_RAM, REGIONS
from utils import compare_addrs, read_yaml, read_yamls, write_yaml

# map types produced by decomp.py
DECOMP_MAP_TYPES = (MAP_CODE, MAP_DATA, MAP_RAM)
# enrichment fields to carry over from existing data, per map type
CARRY_FIELDS = {
    MAP_CODE: ("params", "return"),
    MAP_DATA: ("type", "count"),
    MAP_RAM: ("type", "count"),
}


def load_region(path: str, map_type: str):
    """Load a decomp map file as a list of entries (empty if missing)."""
    fp = os.path.join(path, map_type + ".yml")
    if not os.path.isfile(fp):
        return []
    data = read_yaml(fp)
    return data if isinstance(data, list) else []


def versioned(values: dict, present, all_regions):
    """Return a plain int when the value is identical across every region the
    game supports, otherwise a {region: value} dict limited to present regions.
    """
    vals = set(values[r] for r in present)
    if len(present) == len(all_regions) and len(vals) == 1:
        return next(iter(vals))
    # order keys by canonical region order
    return {r: values[r] for r in REGIONS if r in values}


def merge_map(region_entries: dict, all_regions, carry_index: dict):
    """region_entries: {region: [entry, ...]}. Returns merged list."""
    # index each region's entries by label
    by_label = {}
    order = []
    for region in all_regions:
        for entry in region_entries.get(region, []):
            label = entry["label"]
            if label not in by_label:
                by_label[label] = {}
                order.append(label)
            by_label[label][region] = entry

    merged = []
    for label in order:
        per_region = by_label[label]
        present = [r for r in all_regions if r in per_region]
        # pick a canonical base entry (prefer U, then first supported region)
        base_region = "U" if "U" in per_region else present[0]
        base = dict(per_region[base_region])
        # version addr and size
        addrs = {r: per_region[r]["addr"] for r in present}
        base["addr"] = versioned(addrs, present, all_regions)
        if all("size" in per_region[r] for r in present):
            sizes = {r: per_region[r]["size"] for r in present}
            base["size"] = versioned(sizes, present, all_regions)
        # carry over enrichment from existing data by label
        old = carry_index.get(label)
        if old:
            # preserve a manually edited description
            if old.get("desc") and old["desc"] != old.get("label"):
                base["desc"] = old["desc"]
            for field in CARRY_FIELDS_FOR(base):
                if base.get(field) in (None, "") and old.get(field) not in (None, ""):
                    base[field] = old[field]
        merged.append(base)
    # sort by address so the info file stays in address order
    merged.sort(key=cmp_to_key(compare_addrs))
    return merged


def CARRY_FIELDS_FOR(entry):
    # code entries have a 'mode'; data/ram entries have a 'type'
    if "mode" in entry:
        return CARRY_FIELDS[MAP_CODE]
    return CARRY_FIELDS[MAP_DATA]


def build_carry_index(carry_dir: str, map_type: str):
    """Index existing entries by label for enrichment carryover."""
    if not carry_dir or not os.path.isdir(carry_dir):
        return {}
    fp = os.path.join(carry_dir, map_type + ".yml")
    if not os.path.isfile(fp):
        return {}
    index = {}
    data = read_yaml(fp)
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and "label" in entry:
                index[entry["label"]] = entry
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", required=True)
    parser.add_argument("--dst", required=True,
                        help="output info directory (yaml/<game>)")
    parser.add_argument("--carryover", default=None,
                        help="existing info directory to copy type/param info from")
    parser.add_argument("--region", action="append", required=True,
                        metavar="REGION:PATH",
                        help="region letter and decomp output dir, e.g. U:/tmp/fe8u_out")
    args = parser.parse_args()

    regions = []
    region_dirs = {}
    for spec in args.region:
        region, path = spec.split(":", 1)
        regions.append(region)
        region_dirs[region] = path
    # keep canonical region order
    all_regions = [r for r in REGIONS if r in regions]

    os.makedirs(args.dst, exist_ok=True)
    for map_type in DECOMP_MAP_TYPES:
        region_entries = {
            r: load_region(region_dirs[r], map_type) for r in all_regions
        }
        carry_index = build_carry_index(args.carryover, map_type)
        merged = merge_map(region_entries, all_regions, carry_index)
        write_yaml(os.path.join(args.dst, map_type + ".yml"), merged, map_type)
        print(f"{args.game} {map_type}: {len(merged)} entries")


if __name__ == "__main__":
    main()
