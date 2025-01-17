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

def readSectionsFromElf(path: str) -> None:
    try:
        result = subprocess.run(['arm-none-eabi-readelf', '-S', path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        print(err)
        print(err.stderr)
        sys.exit(1)
    lines = result.stdout.splitlines()
    result = re.search( r'There are (\d+) section headers', lines[0], re.I)
    if result:
        num = int(result.group(1))
    else:
        print('cannot find section num')
        print(lines[0])
        sys.exit(1)
    for i in range(5, 4 + num):
        Name, _, Addr, _, Size = lines[i].split(']')[1].split()[:5]
        sections[Name] = {'addr': int(Addr, 16), 'size': int(Size, 16)}

def readSymbolsFromElf(path: str) -> None:
    try:
        result = subprocess.run(['arm-none-eabi-nm', '-S', '-l', '-n', '-f', 'sysv', path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        print(err)
        print(err.stderr)
        sys.exit(1)
    lines = result.stdout.splitlines()
    for i in range(6, len(lines)):
        Name, Value, _, Type, Size, _, Last = [x.strip() for x in lines[i].split('|')]
        lasts = Last.split()
        Section = ''
        Line = ''
        if len(lasts) >= 2:
            Line = lasts[1]
        if len(lasts) >= 1:
            Section = lasts[0]
        if Section not in ('ROM', 'EWRAM', 'IWRAM'):
            continue
        Value = int(Value, 16)
        if Size == '':
            Size = sections[Section]['addr'] + sections[Section]['size']
            if i < len(lines) - 1:
                Size = min(Size, int(lines[i + 1].split('|')[1].strip(), 16))
            Size -= Value
        else:
            Size = int(Size, 16)
        MapType = MAP_RAM
        if Section == 'ROM':
            if Type == 'FUNC':
                MapType = MAP_CODE
            else:
                MapType = MAP_DATA
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
    readSectionsFromElf(srcPath + '.elf')
    readSymbolsFromElf(srcPath + '.elf')
    readDeclFromSrc(srcPath + '.c')
    writeDataToYaml(dstPath, MAP_CODE)
    writeDataToYaml(dstPath, MAP_DATA)
    writeDataToYaml(dstPath, MAP_RAM)
    return 0

if __name__ == '__main__':
    sys.exit(main())
