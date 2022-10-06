import os
import re
import sys
import subprocess
import pycparser
from pycparserext.ext_c_parser import GnuCParser
from pycparserext.ext_c_generator import GnuCGenerator
from constants import *
from utils import write_yaml

sections = {}

symbols = {}

class MyVisitor(GnuCGenerator):
    def visit_FuncDef(self, n):
        name = n.decl.name
        if name in symbols:
            retVal = self.visit(n.decl.type.type)
            if retVal != '' and retVal != 'void':
                symbols[name]['return'] = {'desc': 'result', 'type': retVal}
            args = self.visit(n.decl.type.args)
            if args != '' and args != 'void':
                symbols[name]['params'] = []
                for arg in args.split(', '):
                    separator = ' '
                    if '*' in arg:
                        separator = '*'
                    arr = arg.split(separator)
                    argName = arr[-1]
                    argType = separator.join(arr[:-1])
                    if separator == '*':
                        argType += '*'
                    symbols[name]['params'].append({'desc': argName, 'type': argType})
        decl = self.visit(n.decl)
        self.indent_level = 0
        body = self.visit(n.body)
        if n.param_decls:
            knrdecls = ';\n'.join(self.visit(p) for p in n.param_decls)
            return decl + '\n' + knrdecls + ';\n' + body + '\n'
        else:
            return decl + '\n' + body + '\n'


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
    write_yaml(os.path.join(dstPath, mapType + '.yml'), data, mapType)

def main() -> int:
    # you need to install devkitARM or GNU Arm Embedded Toolchain and add it to your env PATH first
    srcPath = sys.argv[1]
    dstPath = sys.argv[2]
    readSectionsFromElf(srcPath + '.elf')
    readSymbolsFromElf(srcPath + '.elf')
    readDeclFromSrc(srcPath + '.c')
    writeDataToYaml(dstPath, MAP_CODE)
    return 0

if __name__ == '__main__':
    sys.exit(main())
