#!/usr/bin/env python3
"""Extract DWARF enum and struct definitions from GBA FE decomp ELFs."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from struct import unpack_from
from typing import Optional

import yaml


DEFAULT_ELFS = {
    "fe6": "/home/laqieer/fireemblem6j/fe6.elf",
    "fe8": "/home/laqieer/fireemblem8u/fireemblem8.elf",
}

LABEL_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_.]*$")
HEADER_RE = re.compile(r"^\s*<(\d+)><([0-9a-fA-F]+)>: Abbrev Number: (\d+)(?: \((DW_TAG_[^)]+)\))?")
ATTR_RE = re.compile(r"^\s*<[0-9a-fA-F]+>\s+(DW_AT_[A-Za-z0-9_]+)\s*:\s*(.*)$")
REF_RE = re.compile(r"<0x([0-9a-fA-F]+)>")

DW_TAGS = {
    0x01: "DW_TAG_array_type",
    0x04: "DW_TAG_enumeration_type",
    0x05: "DW_TAG_formal_parameter",
    0x0D: "DW_TAG_member",
    0x0F: "DW_TAG_pointer_type",
    0x11: "DW_TAG_compile_unit",
    0x13: "DW_TAG_structure_type",
    0x15: "DW_TAG_subroutine_type",
    0x16: "DW_TAG_typedef",
    0x17: "DW_TAG_union_type",
    0x21: "DW_TAG_subrange_type",
    0x24: "DW_TAG_base_type",
    0x26: "DW_TAG_const_type",
    0x28: "DW_TAG_enumerator",
    0x2E: "DW_TAG_subprogram",
    0x34: "DW_TAG_variable",
    0x35: "DW_TAG_volatile_type",
}

DW_ATTRS = {
    0x01: "DW_AT_sibling",
    0x02: "DW_AT_location",
    0x03: "DW_AT_name",
    0x0B: "DW_AT_byte_size",
    0x10: "DW_AT_stmt_list",
    0x11: "DW_AT_low_pc",
    0x12: "DW_AT_high_pc",
    0x13: "DW_AT_language",
    0x1C: "DW_AT_const_value",
    0x1B: "DW_AT_comp_dir",
    0x25: "DW_AT_producer",
    0x27: "DW_AT_prototyped",
    0x2F: "DW_AT_upper_bound",
    0x38: "DW_AT_data_member_location",
    0x3A: "DW_AT_decl_file",
    0x3B: "DW_AT_decl_line",
    0x3E: "DW_AT_encoding",
    0x3F: "DW_AT_external",
    0x40: "DW_AT_frame_base",
    0x49: "DW_AT_type",
}

DW_FORM_ADDR = 0x01
DW_FORM_BLOCK2 = 0x03
DW_FORM_BLOCK4 = 0x04
DW_FORM_DATA2 = 0x05
DW_FORM_DATA4 = 0x06
DW_FORM_DATA8 = 0x07
DW_FORM_STRING = 0x08
DW_FORM_BLOCK = 0x09
DW_FORM_BLOCK1 = 0x0A
DW_FORM_DATA1 = 0x0B
DW_FORM_FLAG = 0x0C
DW_FORM_SDATA = 0x0D
DW_FORM_STRP = 0x0E
DW_FORM_UDATA = 0x0F
DW_FORM_REF_ADDR = 0x10
DW_FORM_REF1 = 0x11
DW_FORM_REF2 = 0x12
DW_FORM_REF4 = 0x13
DW_FORM_REF8 = 0x14
DW_FORM_REF_UDATA = 0x15
DW_FORM_INDIRECT = 0x16


@dataclass(slots=True)
class Die:
    offset: int
    level: int
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[int] = field(default_factory=list)


class DwarfDump:
    def __init__(self, elf: str, readelf: str = "arm-none-eabi-readelf") -> None:
        self.elf = elf
        self.readelf = readelf
        self.dies: dict[int, Die] = {}

    def parse(self) -> None:
        self._parse_readelf()
        if not self.dies:
            self._parse_raw_dwarf()

    def _parse_readelf(self) -> None:
        cmd = [self.readelf, "--debug-dump=info", self.elf]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None

        stack: list[Optional[int]] = []
        current: Optional[Die] = None

        for line in proc.stdout:
            if m := HEADER_RE.match(line):
                level = int(m.group(1))
                abbrev = int(m.group(3))
                if abbrev == 0 or not m.group(4):
                    current = None
                    if level < len(stack):
                        stack = stack[:level]
                    continue

                off = int(m.group(2), 16)
                die = Die(offset=off, level=level, tag=m.group(4))
                self.dies[off] = die

                if level > 0 and level - 1 < len(stack):
                    parent_off = stack[level - 1]
                    if parent_off in self.dies:
                        self.dies[parent_off].children.append(off)

                if len(stack) <= level:
                    stack.extend([None] * (level + 1 - len(stack)))
                stack[level] = off
                del stack[level + 1 :]
                current = die
                continue

            if current is not None and (m := ATTR_RE.match(line)):
                current.attrs[m.group(1)] = clean_attr_value(m.group(2))

        proc.wait()

    def _parse_raw_dwarf(self) -> None:
        sections = read_elf_sections(self.elf)
        info = sections.get(".debug_info")
        abbrev_data = sections.get(".debug_abbrev")
        if not info or not abbrev_data:
            raise RuntimeError(f"{self.elf} has no usable DWARF info/abbrev sections")
        debug_str = sections.get(".debug_str", b"")
        abbrev_cache: dict[int, dict[int, tuple[str, bool, list[tuple[str, int]]]]] = {}

        pos = 0
        while pos + 11 <= len(info):
            cu_start = pos
            length = u32(info, pos)
            pos += 4
            if length == 0 or pos + length > len(info):
                break
            cu_end = pos + length
            version = u16(info, pos)
            pos += 2
            abbrev_off = u32(info, pos)
            pos += 4
            addr_size = info[pos]
            pos += 1
            if version != 2:
                pos = cu_end
                continue

            table = abbrev_cache.get(abbrev_off)
            if table is None:
                table = parse_abbrev_table(abbrev_data, abbrev_off)
                abbrev_cache[abbrev_off] = table

            stack: list[int] = []
            while pos < cu_end:
                die_off = pos
                code, pos = read_uleb(info, pos)
                if code == 0:
                    if stack:
                        stack.pop()
                    continue
                abbrev = table.get(code)
                if abbrev is None:
                    break
                tag, has_children, specs = abbrev
                die = Die(offset=die_off, level=len(stack), tag=tag)
                self.dies[die_off] = die
                if stack and stack[-1] in self.dies:
                    self.dies[stack[-1]].children.append(die_off)

                for attr_name, form in specs:
                    value, pos = read_form_value(info, pos, form, cu_start, addr_size, debug_str)
                    if attr_name in (
                        "DW_AT_name",
                        "DW_AT_type",
                        "DW_AT_byte_size",
                        "DW_AT_const_value",
                        "DW_AT_data_member_location",
                        "DW_AT_upper_bound",
                    ):
                        die.attrs[attr_name] = value

                if has_children:
                    stack.append(die_off)
            pos = cu_end

    def type_string(self, off: Optional[int], seen: Optional[set[int]] = None) -> tuple[str, Optional[int]]:
        if off is None or off not in self.dies:
            return "void", None
        if seen is None:
            seen = set()
        if off in seen:
            return "void", None
        seen.add(off)

        die = self.dies[off]
        tag = die.tag
        attrs = die.attrs

        if tag == "DW_TAG_base_type":
            return attrs.get("DW_AT_name") or "void", None

        if tag == "DW_TAG_typedef":
            return attrs.get("DW_AT_name") or self.type_string(ref_attr(attrs.get("DW_AT_type")), seen)[0], None

        if tag == "DW_TAG_pointer_type":
            inner, _ = self.type_string(ref_attr(attrs.get("DW_AT_type")), seen)
            return f"{inner} *", None

        if tag == "DW_TAG_array_type":
            inner, inner_count = self.type_string(ref_attr(attrs.get("DW_AT_type")), seen)
            dims: list[Optional[int]] = []
            for child in die.children:
                cdie = self.dies.get(child)
                if cdie and cdie.tag == "DW_TAG_subrange_type":
                    dims.append(array_count(cdie.attrs.get("DW_AT_upper_bound")))
            suffix = ""
            product = inner_count
            for idx, dim in enumerate(dims or [None]):
                lead = "" if inner.endswith("*") or idx else " "
                suffix += f"{lead}[{dim}]" if dim is not None else f"{lead}[]"
                if dim is not None:
                    product = dim if product is None else product * dim
                else:
                    product = None
            return inner + suffix, product

        if tag in ("DW_TAG_const_type", "DW_TAG_volatile_type"):
            inner, count = self.type_string(ref_attr(attrs.get("DW_AT_type")), seen)
            prefix = "const" if tag == "DW_TAG_const_type" else "volatile"
            return f"{prefix} {inner}", count

        if tag == "DW_TAG_structure_type":
            return f"struct {attrs['DW_AT_name']}" if attrs.get("DW_AT_name") else "struct", None

        if tag == "DW_TAG_union_type":
            return f"union {attrs['DW_AT_name']}" if attrs.get("DW_AT_name") else "union", None

        if tag == "DW_TAG_enumeration_type":
            return f"enum {attrs['DW_AT_name']}" if attrs.get("DW_AT_name") else "enum", None

        if tag == "DW_TAG_subroutine_type":
            return "void", None

        return attrs.get("DW_AT_name") or "void", None

    def enums(self) -> list[dict]:
        out: list[dict] = []
        seen_names: set[str] = set()
        for die in self.dies.values():
            if die.tag != "DW_TAG_enumeration_type":
                continue
            name = die.attrs.get("DW_AT_name")
            if not valid_label(name) or name in seen_names:
                continue
            vals = []
            for child in die.children:
                cdie = self.dies.get(child)
                if not cdie or cdie.tag != "DW_TAG_enumerator":
                    continue
                member = cdie.attrs.get("DW_AT_name")
                val = parse_int(cdie.attrs.get("DW_AT_const_value"))
                if not valid_label(member) or val is None:
                    continue
                vals.append({"desc": member, "label": member, "val": hex_int(val & 0xFFFFFFFF)})
            if vals:
                out.append({"desc": name, "label": name, "vals": vals})
                seen_names.add(name)
        return out

    def structs(self) -> list[dict]:
        out: list[dict] = []
        seen_names: set[str] = set()
        for die in self.dies.values():
            if die.tag != "DW_TAG_structure_type":
                continue
            name = die.attrs.get("DW_AT_name")
            size = parse_int(die.attrs.get("DW_AT_byte_size"))
            if not valid_label(name) or name in seen_names or size is None:
                continue
            vars_out = []
            for child in die.children:
                cdie = self.dies.get(child)
                if not cdie or cdie.tag != "DW_TAG_member":
                    continue
                member = cdie.attrs.get("DW_AT_name")
                offset = data_member_offset(cdie.attrs.get("DW_AT_data_member_location"))
                if not valid_label(member) or offset is None:
                    continue
                type_text, count = self.type_string(ref_attr(cdie.attrs.get("DW_AT_type")))
                var = {
                    "desc": member,
                    "label": member,
                    "type": type_text or "void",
                    "offset": hex_int(offset),
                }
                if count is not None:
                    var["count"] = hex_int(count)
                vars_out.append(var)
            if vars_out:
                out.append({"desc": name, "label": name, "size": hex_int(size), "vars": vars_out})
                seen_names.add(name)
        return out


def clean_attr_value(value: str) -> str:
    value = value.strip()
    # readelf sometimes prefixes indirect strings as "(indirect string, offset: 0x...): value".
    if "): " in value:
        value = value.rsplit("): ", 1)[1]
    return value.strip()


def u16(data: bytes, off: int) -> int:
    return unpack_from("<H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return unpack_from("<I", data, off)[0]


def read_cstring(data: bytes, off: int) -> tuple[str, int]:
    end = data.find(b"\0", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("utf-8", "replace"), end + 1


def read_uleb(data: bytes, off: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while off < len(data):
        byte = data[off]
        off += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    return result, off


def read_sleb(data: bytes, off: int) -> tuple[int, int]:
    result = 0
    shift = 0
    size = 8 * len(data)
    byte = 0
    while off < len(data):
        byte = data[off]
        off += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    if shift < size and byte & 0x40:
        result |= -1 << shift
    return result, off


def read_elf_sections(path: str) -> dict[str, bytes]:
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise RuntimeError(f"{path} is not a little-endian ELF32 file")

    shoff = u32(data, 0x20)
    shentsize = u16(data, 0x2E)
    shnum = u16(data, 0x30)
    shstrndx = u16(data, 0x32)
    if shstrndx >= shnum:
        return {}

    def shdr(idx: int) -> tuple[int, int, int]:
        base = shoff + idx * shentsize
        return u32(data, base), u32(data, base + 0x10), u32(data, base + 0x14)

    _, str_off, str_size = shdr(shstrndx)
    shstr = data[str_off : str_off + str_size]

    sections: dict[str, bytes] = {}
    for idx in range(shnum):
        name_off, sec_off, sec_size = shdr(idx)
        name, _ = read_cstring(shstr, name_off)
        if name.startswith(".debug_"):
            sections[name] = data[sec_off : sec_off + sec_size]
    return sections


def parse_abbrev_table(data: bytes, off: int) -> dict[int, tuple[str, bool, list[tuple[str, int]]]]:
    table: dict[int, tuple[str, bool, list[tuple[str, int]]]] = {}
    pos = off
    while pos < len(data):
        code, pos = read_uleb(data, pos)
        if code == 0:
            break
        tag_num, pos = read_uleb(data, pos)
        if pos >= len(data):
            break
        has_children = data[pos] != 0
        pos += 1
        specs: list[tuple[str, int]] = []
        while pos < len(data):
            attr_num, pos = read_uleb(data, pos)
            form, pos = read_uleb(data, pos)
            if attr_num == 0 and form == 0:
                break
            specs.append((DW_ATTRS.get(attr_num, f"DW_AT_{attr_num:x}"), form))
        table[code] = (DW_TAGS.get(tag_num, f"DW_TAG_{tag_num:x}"), has_children, specs)
    return table


def read_form_value(
    data: bytes,
    off: int,
    form: int,
    cu_start: int,
    addr_size: int,
    debug_str: bytes,
):
    while form == DW_FORM_INDIRECT:
        form, off = read_uleb(data, off)

    if form == DW_FORM_ADDR:
        size = addr_size
        value = int.from_bytes(data[off : off + size], "little")
        return value, off + size
    if form == DW_FORM_BLOCK2:
        size = u16(data, off)
        off += 2
        return decode_location_block(data[off : off + size]), off + size
    if form == DW_FORM_BLOCK4:
        size = u32(data, off)
        off += 4
        return decode_location_block(data[off : off + size]), off + size
    if form == DW_FORM_DATA2:
        return u16(data, off), off + 2
    if form == DW_FORM_DATA4:
        return u32(data, off), off + 4
    if form == DW_FORM_DATA8:
        return int.from_bytes(data[off : off + 8], "little"), off + 8
    if form == DW_FORM_STRING:
        return read_cstring(data, off)
    if form == DW_FORM_BLOCK:
        size, off = read_uleb(data, off)
        return decode_location_block(data[off : off + size]), off + size
    if form == DW_FORM_BLOCK1:
        size = data[off]
        off += 1
        return decode_location_block(data[off : off + size]), off + size
    if form == DW_FORM_DATA1:
        return data[off], off + 1
    if form == DW_FORM_FLAG:
        return data[off], off + 1
    if form == DW_FORM_SDATA:
        return read_sleb(data, off)
    if form == DW_FORM_STRP:
        str_off = u32(data, off)
        return read_cstring(debug_str, str_off)[0], off + 4
    if form == DW_FORM_UDATA:
        return read_uleb(data, off)
    if form == DW_FORM_REF_ADDR:
        value = u32(data, off)
        return value, off + 4
    if form == DW_FORM_REF1:
        return cu_start + data[off], off + 1
    if form == DW_FORM_REF2:
        return cu_start + u16(data, off), off + 2
    if form == DW_FORM_REF4:
        return cu_start + u32(data, off), off + 4
    if form == DW_FORM_REF8:
        return cu_start + int.from_bytes(data[off : off + 8], "little"), off + 8
    if form == DW_FORM_REF_UDATA:
        value, off = read_uleb(data, off)
        return cu_start + value, off

    raise RuntimeError(f"unsupported DWARF form 0x{form:x}")


def decode_location_block(block: bytes):
    if not block:
        return None
    # DW_OP_plus_uconst
    if block[0] == 0x23:
        value, _ = read_uleb(block, 1)
        return value
    return block


def valid_label(value: Optional[str]) -> bool:
    return bool(value and LABEL_RE.match(value))


def ref_attr(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    if not value:
        return None
    match = REF_RE.search(value)
    return int(match.group(1), 16) if match else None


def parse_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = value.strip().split()[0]
    try:
        return int(text, 0)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return None


def array_count(value: Optional[str]) -> Optional[int]:
    upper = parse_int(value)
    return None if upper is None else upper + 1


def data_member_offset(value) -> Optional[int]:
    if isinstance(value, int):
        return value
    if not value:
        return None
    if m := re.search(r"DW_OP_plus_uconst:\s*(-?(?:0x)?[0-9a-fA-F]+)", value):
        return parse_int(m.group(1))
    if "byte block:" in value:
        block = value.split("byte block:", 1)[1].split("\t", 1)[0].split("(", 1)[0].strip()
        parts = block.split()
        if parts:
            try:
                return int(parts[-1], 16)
            except ValueError:
                return parse_int(parts[-1])
    return parse_int(value)


def hex_int(value: int) -> str:
    return f"{value:X}"


def write_outputs(dst: str, game: str, enums: list[dict], structs: list[dict]) -> None:
    json_dir = os.path.join(dst, "json", game)
    yaml_dir = os.path.join(dst, "yaml", game)
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(yaml_dir, exist_ok=True)

    outputs = (
        ("enums", enums),
        ("structs", structs),
    )
    for name, data in outputs:
        with open(os.path.join(json_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        with open(os.path.join(yaml_dir, f"{name}.yml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, width=math.inf, allow_unicode=True, sort_keys=False)


def generate(elf: str, game: str, dst: str, readelf: str) -> tuple[int, int]:
    dump = DwarfDump(elf, readelf)
    dump.parse()
    enums = dump.enums()
    structs = dump.structs()
    write_outputs(dst, game, enums, structs)
    return len(enums), len(structs)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("elf", nargs="?", help="ELF to read; omit to regenerate the known FE6/FE8 ELFs")
    ap.add_argument("game", nargs="?", choices=sorted(DEFAULT_ELFS), help="game id for a single ELF")
    ap.add_argument("--dst", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--readelf", default="arm-none-eabi-readelf")
    args = ap.parse_args(argv)

    if bool(args.elf) != bool(args.game):
        ap.error("provide both <elf> and <game>, or neither")

    jobs = {args.game: args.elf} if args.elf else DEFAULT_ELFS
    for game, elf in jobs.items():
        enum_count, struct_count = generate(elf, game, args.dst, args.readelf)
        print(f"{game}: wrote {enum_count} enums, {struct_count} structs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
