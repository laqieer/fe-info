import os
import re
import sys
import subprocess
import pycparser
from pycparser.c_ast import EllipsisParam, TypeDecl, ArrayDecl
from pycparserext.ext_c_parser import GnuCParser
from pycparserext.ext_c_generator import GnuCGenerator
from constants import *
from utils import write_yaml

sections = {}
symbols = {}
enums = {}

class MyVisitor(GnuCGenerator):
    def visit_FuncDef(self, n):
        name = n.decl.name
        if name in symbols:
            retVal = self.visit(n.decl.type.type)
            if retVal != '' and retVal != 'void':
                symbols[name]['return'] = {'desc': 'result', 'type': retVal}
            if n.decl.type.args is not None:
                for param in n.decl.type.args.params:
                    if isinstance(param, EllipsisParam):
                        paramName = '...'
                        paramType = 'varargs'
                    else:
                        paramName = param.name
                        paramType = self.visit(param.type)
                    if paramName is not None and paramType != 'void':
                        if 'params' not in symbols[name]:
                            symbols[name]['params'] = []
                        symbols[name]['params'].append({'desc': paramName, 'type': paramType})
        return super().visit_FuncDef(n)

    def visit_Decl(self, n, no_type=False):
        # no_type is used when a Decl is part of a DeclList, where the type is
        # explicitly only for the first declaration in a list.
        if not no_type and n.name in symbols and symbols[n.name]['mapType'] != MAP_CODE and 'type' not in symbols[n.name]:
            symbols[n.name]['type'] = self.visit(n.type)
            if n.bitsize:
                symbols[n.name]['type'] += ':' + self.visit(n.bitsize)
        return super().visit_Decl(n, no_type)

    def visit_Enumerator(self, n):
        if n.value:
            v = self.visit(n.value)
            if v in enums:
                v = enums[v]
            enums[n.name] = v
        return super().visit_Enumerator(n)

    def _generate_type(self, n, modifiers=[], emit_declname = True):
        if emit_declname and type(n) == TypeDecl and n.declname and n.declname in symbols:
            for modifier in modifiers:
                if isinstance(modifier, ArrayDecl):
                    if modifier.dim:
                        symbols[n.declname]['count'] = self.visit(modifier.dim)
        return super()._generate_type(n, modifiers, emit_declname)


def readDeclFromSrc(path: str) -> None:
    p = GnuCParser()
    ast = pycparser.parse_file(path, parser=p, use_cpp=True,
                                cpp_args=[r'-Iutils/fake_libc_include',
                                            r'-Itools/agbcc/include',
                                            r'-iquote', r'include',
                                            r'-iquote', r'.'])
    MyVisitor().visit(ast)

# Matches a readelf -SW section row: [ Nr] Name Type Addr Off Size ...
# Requires a non-empty section name, so the NULL row and header are ignored.
SECTION_PAT = re.compile(
    r'^\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)')


def isRamSection(section: str) -> bool:
    # Fire Emblem ROMs place RAM data in IWRAM and the EWRAM overlay/data
    # sections (e.g. ewram_data, ewram_overlay_*). Older linker scripts used
    # a single "EWRAM" section, so accept that too.
    return (section == 'IWRAM' or section == 'EWRAM' or
            section.lower().startswith('ewram'))


def readSectionsFromElf(path: str) -> None:
    try:
        # -W (wide) prevents section names from being truncated as "name[...]"
        result = subprocess.run(['arm-none-eabi-readelf', '-SW', path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        print(err)
        print(err.stderr)
        sys.exit(1)
    for line in result.stdout.splitlines():
        m = SECTION_PAT.match(line)
        if m:
            name, addr, size = m.group(1), m.group(2), m.group(3)
            sections[name] = {'addr': int(addr, 16), 'size': int(size, 16)}

def readSymbolsFromElf(path: str) -> None:
    try:
        result = subprocess.run(['arm-none-eabi-nm', '-S', '-l', '-n', '-f', 'sysv', path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        print(err)
        print(err.stderr)
        sys.exit(1)
    # First pass: collect real ROM/RAM symbols (skip *ABS*, *UND*, debug, etc.)
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split('|')
        if len(parts) < 7:
            continue
        Name = parts[0].strip()
        Value = parts[1].strip()
        Type = parts[3].strip()
        Size = parts[4].strip()
        # nm -l appends "section  /path/to/file:line" to the last column
        lasts = parts[6].split()
        if not lasts:
            continue
        Section = lasts[0]
        Line = lasts[1] if len(lasts) >= 2 else ''
        if not (Section == 'ROM' or isRamSection(Section)):
            continue
        try:
            Value = int(Value, 16)
        except ValueError:
            continue
        Size = int(Size, 16) if Size else None
        entries.append([Value, Size, Name, Type, Section, Line])
    # Sort by address so sizes can be inferred from the next symbol
    entries.sort(key=lambda e: e[0])
    # Second pass: infer missing sizes and build the symbol table
    for i, (Value, Size, Name, Type, Section, Line) in enumerate(entries):
        if Size is None:
            sec = sections.get(Section)
            end = sec['addr'] + sec['size'] if sec else Value
            if i + 1 < len(entries) and entries[i + 1][0] > Value:
                end = min(end, entries[i + 1][0])
            Size = end - Value
            if Size < 0:
                Size = 0
        MapType = MAP_RAM
        if Section == 'ROM':
            MapType = MAP_CODE if Type == 'FUNC' else MAP_DATA
        symbols[Name] = {
            'mapType': MapType,
            'addr': Value,
            'size': Size,
            'line': os.path.basename(Line),
        }
        if MapType == MAP_CODE:
            symbols[Name]['mode'] = 'thumb'
            if Name.startswith('ARM_') or Name.startswith('IRAMARM_'):
                symbols[Name]['mode'] = 'arm'

def writeDataToYaml(dstPath, mapType):
    data = []
    for name, symbol in symbols.items():
        if symbol['mapType'] == mapType:
            data.append({
                'desc': name,
                'label': name,
                'addr': symbol['addr'],
                'size': symbol['size'],
                'line': symbol['line'],
            })
            if mapType == MAP_CODE:
                data[-1]['mode'] = symbol['mode']
                data[-1]['params'] = symbol.get('params')
                data[-1]['return'] = symbol.get('return')
            elif mapType in (MAP_DATA, MAP_RAM):
                data[-1]['type'] = symbol.get('type')
                if 'count' in symbol:
                    count = symbol['count']
                    for k, v in enums.items():
                        count = count.replace(k, '(' + v + ')')
                    count = eval(count)
                    data[-1]['count'] = count
                    data[-1]['size'] //= count
    write_yaml(os.path.join(dstPath, mapType + '.yml'), data, mapType)

def main() -> int:
    # you need to install devkitARM or GNU Arm Embedded Toolchain and add it to your env PATH first
    srcPath = sys.argv[1]
    dstPath = sys.argv[2]
    # optional explicit path to a combined C source for type enrichment
    cPath = sys.argv[3] if len(sys.argv) > 3 else srcPath + '.c'
    readSectionsFromElf(srcPath + '.elf')
    readSymbolsFromElf(srcPath + '.elf')
    # Type/param enrichment from C source is optional: the ELF alone yields a
    # complete label/address/size map. Skip gracefully if the source is
    # missing or cannot be parsed.
    if os.path.isfile(cPath):
        try:
            readDeclFromSrc(cPath)
        except Exception as err:
            print(f'warning: skipping type enrichment from {cPath}: {err}',
                  file=sys.stderr)
    else:
        print(f'note: no C source at {cPath}; skipping type enrichment',
              file=sys.stderr)
    writeDataToYaml(dstPath, MAP_CODE)
    writeDataToYaml(dstPath, MAP_DATA)
    writeDataToYaml(dstPath, MAP_RAM)
    return 0

if __name__ == '__main__':
    sys.exit(main())
