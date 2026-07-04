#!/usr/bin/env python3
"""Validate the generated JSON map files against the JSON schemas.

Each json/<game>/<map>.json is validated against schema/<schema>.json,
with ram reusing the data schema. Exits non-zero if any file fails.

Usage: python3 tools/validate_schema.py [--game fe8] [--map data]
"""
import argparse
import json
import os
import sys

try:
    from jsonschema import Draft7Validator, RefResolver
except ImportError:
    sys.exit("jsonschema is required: pip install jsonschema")

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)
SCHEMA_DIR = os.path.join(ROOT, "schema")
JSON_DIR = os.path.join(ROOT, "json")

GAMES = ("fe6", "fe8")
# map file (without extension) -> schema file (without extension)
MAP_TO_SCHEMA = {
    "code": "code",
    "data": "data",
    "ram": "data",
    "enums": "enums",
    "structs": "structs",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_validator(schema_name, defs):
    schema = load(os.path.join(SCHEMA_DIR, schema_name + ".json"))
    resolver = RefResolver.from_schema(defs, store={"urn:definitions": defs})
    return Draft7Validator(schema, resolver=resolver)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", choices=GAMES)
    ap.add_argument("--map", choices=sorted(MAP_TO_SCHEMA))
    args = ap.parse_args()

    defs = load(os.path.join(SCHEMA_DIR, "definitions.json"))
    games = [args.game] if args.game else GAMES
    maps = [args.map] if args.map else list(MAP_TO_SCHEMA)

    total_errors = 0
    for game in games:
        for mp in maps:
            path = os.path.join(JSON_DIR, game, mp + ".json")
            if not os.path.isfile(path):
                print(f"SKIP  {game}/{mp}.json (missing)")
                continue
            data = load(path)
            validator = make_validator(MAP_TO_SCHEMA[mp], defs)
            errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
            if errors:
                total_errors += len(errors)
                print(f"FAIL  {game}/{mp}.json: {len(errors)} error(s)")
                for e in errors[:5]:
                    loc = "/".join(str(p) for p in e.absolute_path)
                    print(f"      [{loc}] {e.message}")
                if len(errors) > 5:
                    print(f"      ... and {len(errors) - 5} more")
            else:
                print(f"OK    {game}/{mp}.json ({len(data)} entries)")

    if total_errors:
        print(f"\n{total_errors} schema error(s)")
        return 1
    print("\nAll files valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
