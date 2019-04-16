#!/usr/bin/env python3
"""
Тесты на все модули.
"""

import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.pardir))

from defrag.service_classes import BootSectorCommon
from defrag.service_classes import BootSectorExtended12or16
from defrag.service_classes import BootSectorExtended32
from defrag.service_classes import FileSystemInfo
from defrag.file_system_processor import FileSystemProcessor
from defrag.fragmentator import Fragmentator
from defrag.defragmentator import Defragmentator
from defrag.error_creator import ErrorCreator
from defrag.journaler import Journaler


class LogicalTests(unittest.TestCase):
    fat_16_filename = '_sample_fat16.vhd.test'
    fat_32_filename = '_sample_fat32.vhd.test'
    default_journal = 'journal.log'
    test_journal = '_sample.log'

    test_log = """test
TRANSACTION 2
{"cluster_number": 25, "value": 0, "table": null}
TRANSACTION 0
{"cluster_number": 25, "value": 0, "table": null}
TRANSACTION 0
{"cluster_number": 25, "value": 0, "table": 0}
CLOSED
"""

    def _get_file_and_compare_(self, image_filename):
        with open('_sample_text.txt', 'rb') as test_file:
            sample_text = test_file.read()

        fs_processor = FileSystemProcessor(image_filename, journal_file=self.default_journal)
        obtained_text = bytes.join(b'', fs_processor.get_file('_sample_text.txt')).strip(b'\x00')

        self.assertEqual(sample_text, obtained_text)
        self.assertFalse(list(fs_processor.get_file('no such file')))

    def _defragmentation_(self, image_filename):
        fragmentation_level = Defragmentator(image_filename,
                                             journal_file=self.default_journal).calculate_fragmentation_level()
        Fragmentator(image_filename, journal_file=self.default_journal).fragmentation()
        defragmentator = Defragmentator(image_filename, journal_file=self.default_journal)
        defragmentator.defragmentation()
        self.assertAlmostEqual(fragmentation_level, defragmentator.calculate_fragmentation_level(), delta=1)

    def _file_in_only_one_table(self, image_filename):
        table = 0
        file = ErrorCreator(image_filename, journal_file=self.default_journal).create_file_in_only_one_table(table)
        fs_processor = FileSystemProcessor(image_filename, default_table=table, journal_file=self.default_journal)
        self.assertTrue(file.name in set(map(lambda x: x.name, fs_processor.root_directory.contents)))

        file = ErrorCreator(image_filename, journal_file=self.default_journal).create_file_in_only_one_table(table)
        fs_processor = FileSystemProcessor(image_filename, default_table=table + 1, journal_file=self.default_journal)
        self.assertFalse(file.name in set(map(lambda x: x.name, fs_processor.root_directory.contents)))

    def _file_with_bad_cluster_(self, image_filename):
        file = ErrorCreator(image_filename, journal_file=self.default_journal).create_file_with_bad_cluster()
        fs_processor = FileSystemProcessor(image_filename, journal_file=self.default_journal)
        self.assertTrue(file.name in set(map(lambda x: x.name, fs_processor.found_directory.contents)))

    def _file_with_self_loop_(self, image_filename):
        file = ErrorCreator(image_filename, journal_file=self.default_journal).create_file_with_self_loop()
        fs_processor = FileSystemProcessor(image_filename, journal_file=self.default_journal)
        self.assertTrue(file.name in set(map(lambda x: x.name, fs_processor.found_directory.contents)))

    def _intersecting_files_(self, image_filename):
        first, second = ErrorCreator(image_filename, journal_file=self.default_journal).create_intersecting_files()
        fs_processor = FileSystemProcessor(image_filename, journal_file=self.default_journal)
        self.assertTrue(first.name in set(map(lambda x: x.name, fs_processor.found_directory.contents)))
        self.assertTrue(second.name in set(map(lambda x: x.name, fs_processor.found_directory.contents)))

    def test_get_file_fat16(self):
        self._get_file_and_compare_(self.fat_16_filename)

    def test_get_file_fat32(self):
        self._get_file_and_compare_(self.fat_32_filename)

    def test_defragmentation_fat16(self):
        self._defragmentation_(self.fat_16_filename)

    def test_defragmentation_fat32(self):
        self._defragmentation_(self.fat_32_filename)

    def test_file_in_only_one_table_fat16(self):
        self._file_in_only_one_table(self.fat_16_filename)

    def test_file_in_only_one_table_fat32(self):
        self._file_in_only_one_table(self.fat_32_filename)

    def test_file_with_bad_cluster_fat16(self):
        self._file_with_bad_cluster_(self.fat_16_filename)

    def test_file_with_bad_cluster_fat32(self):
        self._file_with_bad_cluster_(self.fat_32_filename)

    def test_file_with_self_loop_fat16(self):
        self._file_with_self_loop_(self.fat_16_filename)

    def test_file_with_self_loop_fat32(self):
        self._file_with_self_loop_(self.fat_32_filename)

    def test_intersecting_files_fat16(self):
        self._intersecting_files_(self.fat_16_filename)

    def test_intersecting_files_fat32(self):
        self._intersecting_files_(self.fat_32_filename)

    def test_journal_recovery(self):
        with open(self.test_journal, 'w') as handle:
            handle.write(self.test_log)

        journal = Journaler('test', self.test_journal)
        types = {0, 2}
        self.assertEqual(2, len(journal.unclosed_transactions))

        for transaction in journal.unclosed_transactions:
            self.assertTrue(transaction[0] in types)
            for event in transaction[1:]:
                self.assertEqual(25, event.cluster_number)


class ParsingTests(unittest.TestCase):
    def test_boot_sector_common(self):
        bs_content = b''
        boot_jump = 'eb9058'
        bs_content += bytes.fromhex(boot_jump)
        name = 'MSDOS5.0'
        bs_content += name.encode('cp866') + bytes(8 - len(name.encode('cp866')))
        bytes_per_sector = 512
        bs_content += bytes_per_sector.to_bytes(2, byteorder='little')
        sector_per_cluster = 4
        bs_content += sector_per_cluster.to_bytes(1, byteorder='little')
        reserved_sectors_count = 32
        bs_content += reserved_sectors_count.to_bytes(2, byteorder='little')
        number_of_fats = 2
        bs_content += number_of_fats.to_bytes(1, byteorder='little')
        root_entry_count = 0
        bs_content += root_entry_count.to_bytes(2, byteorder='little')
        sectors_count_16bit = 0
        bs_content += sectors_count_16bit.to_bytes(2, byteorder='little')
        media_type = 'f8'
        bs_content += bytes.fromhex(media_type)
        sectors_per_fat_16bit = 0
        bs_content += sectors_per_fat_16bit.to_bytes(2, byteorder='little')
        sectors_per_track = 63
        bs_content += sectors_per_track.to_bytes(2, byteorder='little')
        number_of_heads = 255
        bs_content += number_of_heads.to_bytes(2, byteorder='little')
        hidden_sectors_count = 63
        bs_content += hidden_sectors_count.to_bytes(4, byteorder='little')
        sectors_count_32bit = 273042
        bs_content += sectors_count_32bit.to_bytes(4, byteorder='little')
        bs = BootSectorCommon(bs_content)
        self.assertTrue(boot_jump == bs.boot_jump)
        self.assertTrue(name == bs.name)
        self.assertTrue(bytes_per_sector == bs.bytes_per_sector)
        self.assertTrue(sector_per_cluster == bs.sectors_per_cluster)
        self.assertTrue(reserved_sectors_count == bs.reserved_sectors_count)
        self.assertTrue(number_of_fats == bs.number_of_fats)
        self.assertTrue(root_entry_count == bs.root_entry_count)
        self.assertTrue(sectors_count_16bit == bs.sectors_count_16bit)
        self.assertTrue(media_type == bs.media_type)
        self.assertTrue(sectors_per_fat_16bit == bs.sectors_per_fat_16bit)
        self.assertTrue(sectors_per_track == bs.sectors_per_track)
        self.assertTrue(number_of_heads == bs.number_of_heads)
        self.assertTrue(hidden_sectors_count == bs.hidden_sectors_count)
        self.assertTrue(sectors_count_32bit == bs.sectors_count_32bit)

    def test_boot_sector_fat32_ext(self):
        bs_content = b''
        sectors_per_fat_32bit = 532
        bs_content += sectors_per_fat_32bit.to_bytes(4, byteorder='little')
        bs_content += bytes(2)
        fs_version = '0000'
        bs_content += bytes.fromhex(fs_version)
        root_cluster = 2
        bs_content += root_cluster.to_bytes(4, byteorder='little')
        fs_info_sector = 1
        bs_content += fs_info_sector.to_bytes(2, byteorder='little')
        backup_boot_sector = 6
        bs_content += backup_boot_sector.to_bytes(2, byteorder='little')
        bs_content += bytes(12)
        physical_drive_number = 128
        bs_content += physical_drive_number.to_bytes(1, byteorder='little')
        bs_content += bytes(1)
        boot_signature = '29'
        bs_content += bytes.fromhex(boot_signature)
        volume_id = '20bccd50'
        bs_content += bytes.fromhex(volume_id)
        volume_label = 'NO NAME'
        bs_content += volume_label.encode('cp866') + bytes(11 - len(volume_label.encode('cp866')))
        fs_type = 'FAT32'
        bs_content += fs_type.encode('cp866') + bytes(8 - len(fs_type.encode('cp866')))
        bs_content += bytes(420)
        signature = '55aa'
        bs_content += bytes.fromhex(signature)
        bs = BootSectorExtended32(bs_content)
        self.assertTrue(sectors_per_fat_32bit == bs.sectors_per_fat_32bit)
        self.assertTrue(fs_version == bs.fs_version)
        self.assertTrue(root_cluster == bs.root_cluster)
        self.assertTrue(fs_info_sector == bs.fs_info_sector)
        self.assertTrue(backup_boot_sector == bs.backup_boot_sector)
        self.assertTrue(physical_drive_number == bs.physical_drive_number)
        self.assertTrue(boot_signature == bs.boot_signature)
        self.assertTrue(volume_id == bs.volume_id)
        self.assertTrue(volume_label == bs.volume_label)
        self.assertTrue(fs_type == bs.fs_type)
        self.assertTrue(signature == bs.signature)

    def test_boot_sector_fat16_ext(self):
        bs_content = b''
        physical_drive_number = 128
        bs_content += physical_drive_number.to_bytes(1, byteorder='little')
        bs_content += bytes(1)
        boot_signature = '29'
        bs_content += bytes.fromhex(boot_signature)
        volume_id = 'a0309f1e'
        bs_content += bytes.fromhex(volume_id)
        volume_label = 'NO NAME'
        bs_content += volume_label.encode('cp866') + bytes(11 - len(volume_label.encode('cp866')))
        fs_type = 'FAT16'
        bs_content += fs_type.encode('cp866') + bytes(8 - len(fs_type.encode('cp866')))
        bs_content += bytes(448)
        signature = '55aa'
        bs_content += bytes.fromhex(signature)
        bs = BootSectorExtended12or16(bs_content)
        self.assertTrue(physical_drive_number == bs.physical_drive_number)
        self.assertTrue(boot_signature == bs.boot_signature)
        self.assertTrue(volume_id == bs.volume_id)
        self.assertTrue(volume_label == bs.volume_label)
        self.assertTrue(fs_type == bs.fs_type)
        self.assertTrue(signature == bs.signature)

    def test_file_system_info(self):
        fs_info_content = b''
        lead_signature = '41615252'
        fs_info_content += bytes.fromhex(lead_signature)
        fs_info_content += bytes(480)
        structure_signature = '61417272'
        fs_info_content += bytes.fromhex(structure_signature)
        free_cluster_count = 87153
        fs_info_content += free_cluster_count.to_bytes(4, byteorder='little')
        next_free_cluster = 2
        fs_info_content += next_free_cluster.to_bytes(4, byteorder='little')
        fs_info_content += bytes(12)
        trail_signature = 'aa550000'
        fs_info_content += bytes.fromhex(trail_signature)
        fs_info = FileSystemInfo(fs_info_content)
        self.assertTrue(lead_signature == fs_info.lead_signature)
        self.assertTrue(structure_signature == fs_info.structure_signature)
        self.assertTrue(free_cluster_count == fs_info.free_cluster_count)
        self.assertTrue(next_free_cluster == fs_info.next_free_cluster)
        self.assertTrue(trail_signature == fs_info.trail_signature)


if __name__ == '__main__':
    unittest.main()
