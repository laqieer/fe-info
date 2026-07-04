# Fire Emblem Info Files

## About
These files contain labeled RAM and ROM data, along with struct and enum definitions. They're used for the data maps website: https://laqieer.github.io/fe-maps/

## Structure
- `yaml` - Info files in YAML format; large files are split for easier editing
- `json` - Combined YAML files in JSON format; used for the data maps website
- `tools`
  - `utils.py` - Functions for working with YAML data
  - `validator.py` - Script for validating data and converting to JSON
  - `validate_schema.py` - Script for validating the JSON files against the schemas in `schema/`
  - `dwarf_dump.py` - Script for extracting enum and struct definitions from a decomp ELF's DWARF info
  - `dumper.py` - Script for finding and outputing data from a ROM file
  - `constants.py` - Defines constants used by other scripts
  - `decomp.py` - Script for finding data from decomp project and outputing to YAML

Game directories are `fe6` for Binding Blade and `fe8` for The Sacred Stones.

## Data Format
Addresses, sizes, offsets and counts are hexadecimal strings (no `0x` prefix).
When a value differs between regions it is instead an object keyed by region
(`U`, `E`, `J`, `C`, `B`), e.g. `addr: {J: "8000000", U: "8000010"}`.

- ram / rom (`data`)
  - desc
  - label
  - type (may be `null` for labels/symbols that have no C type)
  - addr
  - size
  - count (optional, assume count=1 if not specified)
  - enum (optional)
  - line (optional, source location `file:line`)
- code
  - desc
  - label
  - addr
  - size
  - mode (`thumb` or `arm`)
  - params (`null`, or a list of `{desc, type}`)
  - return (`null`, or `{desc, type}`)
  - line (optional, source location `file:line`)

## Validation
The `schema/` directory contains JSON Schemas describing the generated JSON in
`json/`. Validate every file (requires `jsonschema`):

```
python3 tools/validate_schema.py            # all games and maps
python3 tools/validate_schema.py --game fe8 --map data
```


### Primitive Types
- `u8` - Unsigned 8 bit integer
- `s8` - Signed 8 bit integer
- `flags8` - 8 bit integer used for bit flags
- `bool` - u8 that only takes values 0 (false) or 1 (true)
- `u16` - Unsigned 16 bit integer
- `s16` - Signed 16 bit integer
- `flags16` - 16 bit integer used for bit flags
- `u32` - Unsigned 32 bit integer
- `s32` - Signed 32 bit integer
- `ptr` - 32 bit pointer to an address
- `ascii` - 8 bit ASCII character
- `char` - 16 bit in-game text character
- `lz` - LZ77 compressed
- `gfx` - Graphics, 32 bytes per tile
- `tilemap` - Tilemap, 2 bytes per tile
- `palette` - Palette, 32 bytes per row
- `thumb` - 16 bit THUMB code
- `arm` - 32 bit ARM code
