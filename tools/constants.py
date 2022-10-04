from typing import Dict, Union


YAML_PATH = "../yaml"
YAML_EXT = ".yml"
JSON_PATH = "../json"
JSON_EXT = ".json"

MAP_CODE = "code"
MAP_DATA = "data"
MAP_ENUMS = "enums"
MAP_RAM = "ram"
MAP_STRUCTS = "structs"
MAP_TYPES = (MAP_CODE, MAP_DATA, MAP_ENUMS, MAP_RAM, MAP_STRUCTS)

GAME_FE6 = "fe6"
GAME_FE8 = "fe8"
GAMES = (GAME_FE6, GAME_FE8)

REGION_J = "J"
REGION_U = "U"
REGION_E = "E"
REGIONS = (REGION_J, REGION_U, REGION_E)

ASM_MODES = ("thumb", "arm")

DATA = (
    "desc",
    "label",
    "type",
    "addr",
    "size",
    "count",
    "enum"
)
CODE_VAR = ("desc", "type", "enum")
FIELDS = {
    MAP_ENUMS: (
        "desc",
        "val"
    ),
    MAP_STRUCTS: (
        "size",
        "vars"
    ),
    MAP_CODE: (
        "desc",
        "label",
        "addr",
        "size",
        "mode",
        "params",
        "return",
        "notes"
    ),
    MAP_RAM: DATA,
    MAP_DATA: DATA,
    "addr": REGIONS,
    "size": REGIONS,
    "count": REGIONS,
    "vars":  (
        "desc",
        "type",
        "offset",
        "size",
        "count",
        "enum"
    ),
    "params": CODE_VAR,
    "return": CODE_VAR
}

PRIMITIVES = {
    "u8", "s8", "flags8", "bool",
    "u16", "s16", "flags16",
    "u32", "s32", "ptr",
    "ascii", "char",
    "lz", "gfx", "tilemap", "palette",
    "thumb", "arm"
}

VersionedInt = Union[int, Dict[str, int]]
