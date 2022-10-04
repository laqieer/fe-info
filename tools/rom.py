from typing import Dict
from constants import *


SIZE_8MB = 0x800000
SIZE_16MB = 0x800000
ROM_OFFSET = 0x80000000


class Rom(object):
    def __init__(self, path: str):
        # read file
        with open(path, "rb") as f:
            self.data = f.read()
        # check length
        if len(self.data) not in (SIZE_8MB, SIZE_16MB):
            raise ValueError("ROM should be 8MB or 16MB")
        # check title and code
        title = self.read_ascii(0xA0, 0x10)
        if title == "FIREEMBLEM6\0AFEJ":
            self.game = GAME_FE6
            self.region = REGION_J
        elif title == "FIREEMBLEM8\0BE8J":
            self.game = GAME_FE8
            self.region = REGION_J
        elif title == "FIREEMBLEM2EBE8E":
            self.game = GAME_FE8
            self.region = REGION_U
        elif title == "FIREEMBLEM2PBE8P":
            self.game = GAME_FE8
            self.region = REGION_E
        else:
            raise ValueError("Not a valid GBA FE6/FE8 ROM")

    def read8(self, addr: int) -> int:
        return self.data[addr]

    def read16(self, addr: int) -> int:
        return self.data[addr] | (self.data[addr + 1] << 8)

    def read32(self, addr: int) -> int:
        return (
            self.data[addr] |
            (self.data[addr + 1] << 8) |
            (self.data[addr + 2] << 16) |
            (self.data[addr + 3] << 24)
        )

    def read_ptr(self, addr: int) -> int:
        return (
            self.data[addr] |
            (self.data[addr + 1] << 8) |
            (self.data[addr + 2] << 16) |
            ((self.data[addr + 3] - 8) << 24)
        )

    def read_bytes(self, addr: int, size: int) -> bytes:
        end = addr + size
        return self.data[addr:end]

    def read_ascii(self, addr: int, size: int) -> str:
        return self.read_bytes(addr, size).decode("ascii")

    def code_start(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_FE6:
            addr = 0x230
        elif self.game == GAME_FE8:
            addr = 0x23C
        if virt:
            addr += ROM_OFFSET
        return addr

    def code_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_FE6:
            if self.region == REGION_U:
                addr = 0xA4FA4
            elif self.region == REGION_E:
                addr = 0xA5600
            elif self.region == REGION_J:
                addr = 0xA7290
        elif self.game == GAME_FE8:
            if self.region == REGION_U:
                addr = 0x8C71C
            elif self.region == REGION_E:
                addr = 0x8D3A8
            elif self.region == REGION_J:
                addr = 0x8C778
        if virt:
            addr += ROM_OFFSET
        return addr

    def data_start(self, virt: bool = False) -> int:
        return self.code_end(virt)

    def data_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_FE6:
            if self.region == REGION_U:
                addr = 0x79ECC8
            elif self.region == REGION_E:
                addr = 0x79F524
            elif self.region == REGION_J:
                addr = 0x7F145C
        elif self.game == GAME_FE8:
            if self.region == REGION_U:
                addr = 0x760D38
            elif self.region == REGION_E:
                addr = 0x775414
            elif self.region == REGION_J:
                addr = 0x760E48
        if virt:
            addr += ROM_OFFSET
        return addr

    def arm_functions(self) -> Dict[int, int]:
        if self.game == GAME_FE6:
            if self.region == REGION_U:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_E:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_J:
                return {
                    0x3DDC: 0x3E70,
                    0x3E80: 0x3F20,
                    0x3F30: 0x4578,
                    0x457C: 0x4594,
                    0x4598: 0x460C
                }
        elif self.game == GAME_FE8:
            if self.region == REGION_U:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }
            elif self.region == REGION_E:
                return {
                    0x4374: 0x4408,
                    0x4418: 0x44B8,
                    0x44C8: 0x4B10,
                    0x4B14: 0x4B2C,
                    0x4B30: 0x4BA4
                }
            elif self.region == REGION_J:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }

    def find_bytes(self, pat: bytes, start: int = 0) -> int:
        return self.data.find(pat, start)
