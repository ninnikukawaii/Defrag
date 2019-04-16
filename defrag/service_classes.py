#!/usr/bin/env python3
"""
Вспомогательные классы.
"""

from struct import pack
from struct import unpack
from time import time
from time import gmtime
from bitstring import Bits


class FSType:  # pragma: no cover
    """
    Тип файловой системы.
    """
    fat12 = 0
    fat16 = 1
    fat32 = 2

    byte_entry_length = {fat12: 2, fat16: 2, fat32: 4}
    bit_entry_length = {fat12: 12, fat16: 16, fat32: 28}
    type_string = {fat12: 'FAT12', fat16: 'FAT16', fat32: 'FAT32'}

    end_of_file_markers = {fat12: 0x0ff8,
                           fat16: 0xfff8,
                           fat32: 0x0ffffff8}

    bad_cluster_markers = {fat12: 0x0ff7,
                           fat16: 0xfff7,
                           fat32: 0x0ffffff7}


class BootSectorCommon:
    """
    Часть загрузочного сектора, общая для FAT12, FAT16 и FAT32.
    """
    _format_string = '<3s8s1H1B1H1B1H1H1s1H1H1H1I1I'

    def __init__(self, boot_sector_common):
        if len(boot_sector_common) != 36:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, boot_sector_common)

        self.boot_jump = unpacked[0].hex()
        self.name = unpacked[1].decode('cp866', errors='ignore').strip()
        self.bytes_per_sector = unpacked[2]
        self.sectors_per_cluster = unpacked[3]
        self.reserved_sectors_count = unpacked[4]
        self.number_of_fats = unpacked[5]
        self.root_entry_count = unpacked[6]
        self.sectors_count_16bit = unpacked[7]
        self.media_type = unpacked[8].hex()
        self.sectors_per_fat_16bit = unpacked[9]
        self.sectors_per_track = unpacked[10]
        self.number_of_heads = unpacked[11]
        self.hidden_sectors_count = unpacked[12]
        self.sectors_count_32bit = unpacked[13]


class BootSectorExtended12or16:
    """
    Часть загрузочного сектора, уникальная для FAT12 и FAT16.
    """
    _format_string = '<1B1s1s4s11s8s448s2s'

    def __init__(self, boot_sector_extended):
        if len(boot_sector_extended) != 476:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, boot_sector_extended)

        self.physical_drive_number = unpacked[0]
        self.boot_signature = unpacked[2].hex()
        self.volume_id = unpacked[3].hex()
        self.volume_label = unpacked[4].strip(b'\x00').decode('ascii', errors='ignore')
        self.fs_type = unpacked[5].strip(b'\x00').decode('ascii', errors='ignore')
        self.signature = unpacked[7].hex()


class BootSectorExtended32:
    """
    Часть загрузочного сектора, уникальная для FAT32.
    """
    _format_string = '<1I2s2s1I1H1H12s1B1s1s4s11s8s420s2s'

    def __init__(self, boot_sector_extended):
        if len(boot_sector_extended) != 476:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, boot_sector_extended)

        self.sectors_per_fat_32bit = unpacked[0]
        self.extended_flags = unpacked[1]
        self.fs_version = unpacked[2].hex()
        self.root_cluster = unpacked[3]
        self.fs_info_sector = unpacked[4]
        self.backup_boot_sector = unpacked[5]
        self.physical_drive_number = unpacked[7]
        self.boot_signature = unpacked[9].hex()
        self.volume_id = unpacked[10].hex()
        self.volume_label = unpacked[11].strip(b'\x00').decode('cp866', errors='ignore')
        self.fs_type = unpacked[12].strip(b'\x00').decode('cp866', errors='ignore')
        self.signature = unpacked[14].hex()


class FileSystemInfo:
    """
    Сектор информации о файловой системе FAT32.
    """
    _format_string = '<4s480s4s1I1I12s4s'

    def __init__(self, fs_info):
        if len(fs_info) != 512:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, fs_info)

        self.lead_signature = unpacked[0].hex()
        self.structure_signature = unpacked[2].hex()
        self.free_cluster_count = unpacked[3]
        self.next_free_cluster = unpacked[4]
        self.trail_signature = unpacked[6].hex()


class FileAttribute:  # pragma: no cover
    """
    Атрибуты файла.
    """
    read_only = 0
    hidden = 1
    system = 2
    volume_id = 3
    directory = 4
    archive = 5
    device = 6
    reserved = 7

    long_name = {read_only, hidden, system, volume_id}


class DirectoryEntry:
    """
    Запись о файле в директории.
    """
    empty_directory_entry = bytes.fromhex('E5') + bytes(31)
    _format_string = '<11s1s1s1B2s2s2s2s2s2s2s1I'

    def __init__(self, entry):
        if len(entry) != 32:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, entry)

        self.name = unpacked[0]
        self.attributes = self._parse_attributes_(unpacked[1])
        self.creation_time_tenth = unpacked[3]
        self.creation_time = unpacked[4]
        self.creation_date = unpacked[5]
        self.last_access_date = unpacked[6]
        self._first_cluster_high = unpacked[7]
        self.last_write_time = unpacked[8]
        self.last_write_date = unpacked[9]
        self._first_cluster_low = unpacked[10]
        self.file_size = unpacked[11]

        self.first_cluster_number = self._first_cluster_low + self._first_cluster_high
        self.first_cluster_number = int.from_bytes(self.first_cluster_number, byteorder='little')

        self.long_name = FileAttribute.long_name.issubset(self.attributes)
        self.name_encoding = 'cp866'

        self.parent_offset = 0
        self.parent_cluster_index = 0

    @staticmethod
    def _parse_attributes_(attr_byte):
        """
        Парсинг атрибутов файла.
        """
        attr_bits = Bits(bytes=attr_byte).bin[::-1]
        attributes = set()

        for i, bit in enumerate(attr_bits):
            if int(bit):
                attributes.add(i)

        return attributes

    @staticmethod
    def create_attributes_byte(attributes):
        """
        Заполнение байта атрибутов файла.
        """
        attr_bits = ['0'] * 8

        for attr in attributes:
            attr_bits[attr] = '1'

        attr_bits.reverse()
        attr_bits = '0b' + ''.join(attr_bits)
        return Bits(bin=attr_bits).bytes

    @staticmethod
    def create_short_directory_entry(name, first_cluster, is_directory=True, size=0):
        """
        Создание записи в директории с коротким именем name и первым кластером first_cluster.
        """
        name = name.upper()
        name = name.encode(encoding='cp866')
        if len(name) > 11:
            raise ValueError("Слишком длинное имя!")
        name += b' ' * (11 - len(name))

        time_stamp = gmtime(time())
        first_cluster = first_cluster.to_bytes(length=4, byteorder='little')
        attributes = tuple()
        if is_directory:
            attributes = (FileAttribute.directory,)

        return pack(DirectoryEntry._format_string,
                    name,
                    DirectoryEntry.create_attributes_byte(attributes),
                    b'',
                    time_stamp.tm_sec * 2 // 10,
                    DirectoryEntry.format_time(time_stamp),
                    DirectoryEntry.format_date(time_stamp),
                    DirectoryEntry.format_date(time_stamp),
                    first_cluster[2:],
                    DirectoryEntry.format_time(time_stamp),
                    DirectoryEntry.format_date(time_stamp),
                    first_cluster[:2],
                    size)

    @staticmethod
    def format_time(time_stamp):
        """
        Форматировние времени из time_stamp для записи в директорию.
        """
        seconds = time_stamp.tm_sec // 2
        minutes = time_stamp.tm_min
        hours = time_stamp.tm_hour

        return pack('<1I1I1Q', seconds, minutes, hours)

    @staticmethod
    def format_date(time_stamp):
        """
        Форматировние даты из time_stamp для записи в директорию.
        """
        day = time_stamp.tm_mday
        month = time_stamp.tm_mon
        year = time_stamp.tm_year - 1980

        return pack('<1I1I1Q', day, month, year)


class LongName:
    """
    Запись из директории, содержащая часть длинного имени.
    """
    _format_string = '<1B10s1s1B1s12s1H4s'

    def __init__(self, entry):
        if len(entry) != 32:  # pragma: no cover
            raise ValueError

        unpacked = unpack(self._format_string, entry)

        self.order = unpacked[0]
        self.name_pt1 = unpacked[1]
        self.attributes = unpacked[2].hex()
        self.type = unpacked[3]
        self.check_sum = unpacked[4]
        self.name_pt2 = unpacked[5]
        self.name_pt3 = unpacked[7]


class File:
    """
    Абстракция файла.
    """
    def __init__(self, name, first_cluster, attributes, parent, parent_offset,
                 parent_cluster_number, bytes_per_cluster):
        self.name = name
        self.first_cluster = first_cluster
        self.attributes = attributes
        self.parent = parent
        self.parent_offset = parent_offset
        self.parent_cluster_number = parent_cluster_number
        self.bytes_per_cluster = bytes_per_cluster
        self.cluster_count = None

    def get_entries_positions(self):
        """
        Получение позиций записей о файле в директории.
        """
        file_index = self.parent.contents.index(self)
        if file_index == 0:
            start = 0
        else:
            start = self.parent.contents[file_index - 1].parent_offset

        start += 32
        end = self.parent_offset + 32
        return start, end

    @property
    def high_address_offset(self):
        """
        Верхние байты адреса первого кластера файла.
        """
        return self.parent_offset + 20

    @property
    def low_address_offset(self):
        """
        Нижние байты адреса первого кластера файла.
        """
        return self.parent_offset + 26

    @classmethod
    def get_none_file(cls):
        """
        Создание пустого объекта файла.
        """
        return File(None, None, None, None, None, None, None)

    @classmethod
    def is_none_file(cls, file):
        """
        Проверка, что оъект файла является пустым.
        """
        return file.name is None and \
               file.first_cluster is None and \
               file.attributes is None and \
               file.parent is None and \
               file.parent_offset is None and \
               file.parent_cluster_number is None and \
               file.bytes_per_cluster is None


class Directory(File):
    """
    Абстракция директории.
    """
    def __init__(self, name, cluster_chain, attributes, parent, parent_offset,
                 parent_cluster_number, bytes_per_cluster):
        super().__init__(name, cluster_chain, attributes, parent, parent_offset,
                         parent_cluster_number, bytes_per_cluster)
        self.contents = []
        self.number_of_entries = 0


class OccupiedClusterInfo:
    """
    Информация о кластере из цепочки.
    """
    def __init__(self, number, previous_number, next_number, file):
        self.number = number
        self.previous_number = previous_number
        self.next_number = next_number
        self.file = file


class FATErrorType:  # pragma: no cover
    """
    Тип ошибки в таблице FAT.
    """
    self_loop = 0
    cluster_intersection = 1
    bad_cluster = 2
    unclosed_transaction = 3


class FATError:
    """
    Запись об ошибке в таблице FAT.
    """
    def __init__(self, error_type, cluster_number, next_cluster_number=None):
        self.type = error_type
        self.cluster_number = cluster_number
        self.next_cluster_number = next_cluster_number
        self.cluster_info = None


if __name__ == '__main__':  # pragma: no cover
    print('''Это служебный файл.
Запустите file_system_processor.py, error_creator.py, fragmentator.py или defragmentator.py!''')
    exit()
