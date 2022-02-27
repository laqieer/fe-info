# Metroid Fusion and Metroid Zero Mission Info Files

## About
These files contain labeled RAM and ROM data, along with struct and enum definitions. They're used for the data maps website: http://labk.org/maps/

## Structure
- `yaml` - Info files in YAML format; large files are split for easier editing
- `json` - Combined YAML files in JSON format; used for the data maps website
- `utils.py` - Script for validating data and converting to JSON

Game directories are `mf` for Fusion and `zm` for Zero Mission, while `unk` is for unlabeled data.

## Data Format
- ram / rom
  - desc
  - label
  - type
  - addr
  - size (optional)
  - count (optional, assume count=1 if not specified)
  - enum (optional)
- code
  - desc
  - label
  - addr
  - size
  - mode (`thumb` or `arm`)
  - params
  - return
- structs
  - size
  - vars
- enums
  - desc
  - val

### Primitive Types
- `u8` - Unsigned 8 bit integer
- `s8` - Signed 8 bit integer
- `flags8` - 8 bit integer used for bit flags
- `u16` - Unsigned 16 bit integer
- `s16` - Signed 16 bit integer
- `flags16` - 16 bit integer used for bit flags
- `u32` - Unsigned 32 bit integer
- `s32` - Signed 32 bit integer
- `ptr` - Pointer to an address
- `char` - Text character
- `lz` - LZ77 compressed
- `gfx` - Graphics, 32 bytes per tile
- `palette` - Palette, 32 bytes per row
    