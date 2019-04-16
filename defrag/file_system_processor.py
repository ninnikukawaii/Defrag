#!/usr/bin/env python3
"""
Обработка образа диска.
"""

import argparse
from random import randint
from service_classes import FSType
from service_classes import BootSectorCommon
from service_classes import BootSectorExtended12or16
from service_classes import BootSectorExtended32
from service_classes import DirectoryEntry
from service_classes import FileAttribute
from service_classes import LongName
from service_classes import FileSystemInfo
from service_classes import Directory
from service_classes import File
from service_classes import OccupiedClusterInfo
from service_classes import FATError
from service_classes import FATErrorType
from journaler import Journaler
from journaler import JournalEvent
from journaler import TransactionType


class FileSystemProcessor:
    """
    Обработчик файловой системы на образе диска.
    """
    def __init__(self, image_file, remove_corrupted=False, default_table=None, journal_file=None):
        self._image_file_handle = open(image_file, '_mode+b')

        self._journaler = Journaler(image_file, journal_file)
        self._corrupted_clusters = dict()
        self._recover_data_()

        self._default_table = default_table
        self._collect_info_()
        self._determine_fat_type_()
        self._compare_tables_()
        self._fix_tables_()

        self._file_system_traversal_()
        self._correct_errors_(remove_corrupted)
        self._determine_free_space_()

    def find_fat_entry_for_cluster(self, n, fat_number):
        """
        Поиск адреса записи в FAT для кластера n в таблице с номером fat_number.
        """
        if fat_number >= self._bs_common.number_of_fats:
            raise RuntimeWarning("Нет таблиы с таким номером!")
        if n > self.data_clusters_count:
            raise RuntimeWarning("Выход за пределы таблицы!")

        if self.fs_type == FSType.fat12:
            fat_offset = n + n // 2
        elif self.fs_type == FSType.fat16:
            fat_offset = n * 2
        else:
            fat_offset = n * 4

        return (self._bs_common.reserved_sectors_count + fat_number * self._fat_sectors_count) * \
               self._bs_common.bytes_per_sector + fat_offset

    def read_fat_entry_for_cluster(self, n, fat_number):
        """
        Чтение записи в FAT для кластера n в таблице с номером fat_number.
        """
        self._image_file_handle.seek(self.find_fat_entry_for_cluster(n, fat_number))
        entry = self._image_file_handle.read(FSType.byte_entry_length[self.fs_type])
        entry = entry.hex()

        if self.fs_type == FSType.fat32:
            entry = entry[:-2] + '0' + entry[-1]
        elif self.fs_type == FSType.fat12:
            if n % 2 == 0:
                entry = entry[:-1]
            else:
                entry = entry[1:]
            entry += '0'

        entry = bytes.fromhex(entry)
        return entry

    def write_fat_entry_for_cluster(self, n, value, fat_number):
        """
        Изменение записи для кластера n на value в таблице с номером fat_number.
        """
        if value.bit_length() > FSType.bit_entry_length[self.fs_type]:
            raise AttributeError

        byte_value = value.to_bytes(FSType.byte_entry_length[self.fs_type], byteorder='little')
        if self.fs_type == FSType.fat12:
            if n % 2 == 0:
                next_byte = self.read_fat_entry_for_cluster(n - 1, fat_number)
                next_byte = next_byte[:1]
                byte_value = byte_value[1:] + next_byte
            else:
                previous_byte = self.read_fat_entry_for_cluster(n - 1, fat_number)
                previous_byte = previous_byte[-1:]
                byte_value = previous_byte + byte_value[1:]

        self._journaler.open_transaction(TransactionType.write_table)
        self._journaler.report(JournalEvent(n, value, fat_number))
        self._image_file_handle.seek(self.find_fat_entry_for_cluster(n, fat_number))
        self._image_file_handle.write(byte_value)
        self._journaler.close_transaction()

    def write_all_fat_entries_for_cluster(self, n, value):
        """
        Изменение записи для кластера n на value во всех таблицах.
        """
        self._journaler.open_transaction(TransactionType.write_table)
        self._journaler.report(JournalEvent(n, value))
        for i in range(self._bs_common.number_of_fats):
            self.write_fat_entry_for_cluster(n, value, i)
        self._journaler.close_transaction()

    def is_end_of_file(self, entry):
        """
        Кластер является последним в цепочке.
        """
        entry = int.from_bytes(entry, byteorder='little')
        return entry >= FSType.end_of_file_markers[self.fs_type]

    def is_bad_cluster(self, entry):
        """
        Кластер является поврежденным.
        """
        entry = int.from_bytes(entry, byteorder='little')
        return entry == FSType.bad_cluster_markers[self.fs_type]

    def is_reserved_cluster(self, entry):
        """
        Кластер является зарезервированным и не подлежит использованию.
        """
        return not (self.is_end_of_file(entry) or self.is_bad_cluster(entry)) and \
               int.from_bytes(entry, byteorder='little') > self.data_clusters_count - 1

    def get_data_address_for_cluster_number(self, n):
        """
        Получение адреса в памяти для кластера n.
        """
        return (self._first_data_sector + (n - 2) * self._bs_common.sectors_per_cluster) * \
               self._bs_common.bytes_per_sector

    def read_cluster(self, cluster):
        """
        Чтение заданного кластера.
        """
        self._image_file_handle.seek(self.get_data_address_for_cluster_number(cluster))
        return self._image_file_handle.read(self._bs_common.bytes_per_sector * self._bs_common.sectors_per_cluster)

    def write_cluster(self, cluster, data):
        """
        Изменение заданного кластера.
        """
        if len(data) > self.bytes_per_cluster:
            raise ValueError
        elif len(data) < self.bytes_per_cluster:
            data += bytes(self.bytes_per_cluster - len(data))

        self._journaler.open_transaction(TransactionType.write_cluster)
        self._journaler.report(JournalEvent(cluster))
        self._image_file_handle.seek(self.get_data_address_for_cluster_number(cluster))
        self._image_file_handle.write(data)
        self._journaler.close_transaction()

    def get_file(self, filename):
        """
        Получение содержимого файла filename.
        """
        file = self._find_file_(filename)
        if not file:
            return []
        for cluster in self.get_file_cluster_chain(file):
            if self.occupied_clusters[cluster].next_number:
                yield self.read_cluster(cluster)
            else:
                yield self.read_cluster(cluster).strip(bytes.fromhex('00'))

    def swap_clusters(self, first_number, second_number):
        """
        Перестановка содержимого двух кластеров.
        """
        if first_number == second_number:
            raise ValueError("Перестановка кластера с самим собой!")

        first_cluster_entry = self.occupied_clusters.pop(first_number, None)
        second_cluster_entry = self.occupied_clusters.pop(second_number, None)

        first_previous = None
        first_next = None
        second_previous = None
        second_next = None

        first_entry = self.read_fat_entry_for_cluster(first_number, 0)
        second_entry = self.read_fat_entry_for_cluster(second_number, 0)

        if self.is_bad_cluster(first_entry) or self.is_bad_cluster(second_entry):
            raise ValueError("Один из кластеров поврежден!")

        first_entry = int.from_bytes(first_entry, byteorder='little')
        second_entry = int.from_bytes(second_entry, byteorder='little')

        if first_cluster_entry:
            self.occupied_clusters[second_number] = first_cluster_entry
            first_cluster_entry.number = second_number
            first_previous = first_cluster_entry.previous_number
            first_next = first_cluster_entry.next_number
        if second_cluster_entry:
            self.occupied_clusters[first_number] = second_cluster_entry
            second_cluster_entry.number = first_number
            second_previous = second_cluster_entry.previous_number
            second_next = second_cluster_entry.next_number

        if not first_previous and first_cluster_entry:
            self._change_directory_entries_for_file_(second_number, first_cluster_entry.file)
            first_cluster_entry.file.first_cluster = second_number
        if not second_previous and second_cluster_entry:
            self._change_directory_entries_for_file_(first_number, second_cluster_entry.file)
            second_cluster_entry.file.first_cluster = first_number

        if first_previous and first_cluster_entry:
            self.write_all_fat_entries_for_cluster(first_previous, second_number)
            _previous = self.occupied_clusters[first_previous]
            if _previous.number != second_number:
                _previous.next_number = second_number
            else:
                _previous.previous_number = first_number
        if second_previous and second_cluster_entry:
            self.write_all_fat_entries_for_cluster(second_previous, first_number)
            _previous = self.occupied_clusters[second_previous]
            if _previous.number != first_number:
                _previous.next_number = first_number
            else:
                _previous.previous_number = second_number

        if first_next and first_cluster_entry:
            _next = self.occupied_clusters[first_next]
            if _next.number != second_number:
                _next.previous_number = second_number
            else:
                _next.next_number = first_number
            first_entry = first_cluster_entry.next_number

        if second_next and second_cluster_entry:
            _next = self.occupied_clusters[second_next]
            if _next.number != first_number:
                _next.previous_number = first_number
            else:
                _next.next_number = second_number
            second_entry = second_cluster_entry.next_number

        self._journaler.open_transaction(TransactionType.write_both)
        self._journaler.report(JournalEvent(first_number, second_entry))
        self._journaler.report(JournalEvent(second_number, first_entry))

        self.write_all_fat_entries_for_cluster(first_number, second_entry)
        self.write_all_fat_entries_for_cluster(second_number, first_entry)

        first_cluster = self.read_cluster(first_number)
        second_cluster = self.read_cluster(second_number)
        self.write_cluster(first_number, second_cluster)
        self.write_cluster(second_number, first_cluster)
        self._journaler.close_transaction()

    def _collect_info_(self):
        """
        Получение основной информации о системе из загрузочного сектора.
        """
        self._bs_common = BootSectorCommon(self._image_file_handle.read(36))
        self.number_of_fats = self._bs_common.number_of_fats
        self._root_dir_sectors = ((self._bs_common.root_entry_count * 32) +
                                  (self._bs_common.bytes_per_sector - 1)) // self._bs_common.bytes_per_sector

        if self._root_dir_sectors:
            self._bs_extended = BootSectorExtended12or16(self._image_file_handle.read(476))
        else:
            self._bs_extended = BootSectorExtended32(self._image_file_handle.read(476))

        if self._bs_common.sectors_per_fat_16bit:
            self._fat_sectors_count = self._bs_common.sectors_per_fat_16bit
        else:
            self._fat_sectors_count = self._bs_extended.sectors_per_fat_32bit

        if self._bs_common.sectors_count_16bit:
            self._total_sectors_count = self._bs_common.sectors_count_16bit
        else:
            self._total_sectors_count = self._bs_common.sectors_count_32bit

        self.bytes_per_cluster = self._bs_common.bytes_per_sector * self._bs_common.sectors_per_cluster
        self._first_data_sector = self._bs_common.reserved_sectors_count + self._root_dir_sectors + \
                                  self._bs_common.number_of_fats * self._fat_sectors_count
        self._data_sectors_count = self._total_sectors_count - self._first_data_sector
        self._disk_capacity = self._data_sectors_count * self._bs_common.bytes_per_sector
        self.data_clusters_count = self._data_sectors_count // self._bs_common.sectors_per_cluster

    def _recover_data_(self):
        """
        Восстановление из журнала данных после принудительного завершения.
        """
        if not self._journaler.unclosed_transactions:
            return

        for transaction in self._journaler.unclosed_transactions:
            for event in transaction[1:]:
                number = event.cluster_number
                self._corrupted_clusters[number] = [FATError(FATErrorType.unclosed_transaction, number, number)]

    def _determine_fat_type_(self):
        """
        Определение типа FAT по числу кластеров.
        """
        if self.data_clusters_count <= 0:
            raise AttributeError
        elif self.data_clusters_count < 4085:
            self.fs_type = FSType.fat12
        elif self.data_clusters_count < 65525:
            self.fs_type = FSType.fat16
        else:
            self.fs_type = FSType.fat32

        if self.fs_type == FSType.fat32:
            self._image_file_handle.seek(self._bs_extended.fs_info_sector *
                                         self._bs_common.bytes_per_sector)
            self._fs_info = FileSystemInfo(self._image_file_handle.read(512))
            self._root_cluster = self._bs_extended.root_cluster
        else:
            self._root_cluster = -self._root_dir_sectors // self._bs_common.sectors_per_cluster + 2

    def _compare_tables_(self):
        """
        Сравнение записей во всех таблицах.
        """
        self._different_entries = {}
        for i in range(self.data_clusters_count):
            entry = int.from_bytes(self.read_fat_entry_for_cluster(i, 0), byteorder='little')

            for j in range(1, self._bs_common.number_of_fats):
                another_entry = int.from_bytes(self.read_fat_entry_for_cluster(i, j), byteorder='little')
                if entry != another_entry:
                    if i in self._different_entries:
                        self._different_entries[i].add((j, another_entry))
                    else:
                        self._different_entries[i] = {(0, entry), (j, another_entry)}

    def _fix_tables_(self):
        """
        Исправление несовпадений в таблицах.
        """
        if (self._default_table is None or self._default_table < 0 or self._default_table >= self.number_of_fats) \
                and self._different_entries:
            self._ask_user_to_chose_table_()

        for cluster, entries in self._different_entries.items():
            correct_entry = [x[1] for x in entries if x[0] == self._default_table][0]
            self.write_all_fat_entries_for_cluster(cluster, correct_entry)

    def _ask_user_to_chose_table_(self):
        """
        Выбор пользователем правильной таблицы при их несовпадении.
        """
        print('Обнаружено несовпадение записей в разных таблицах!')
        print()
        for cluster, entries in self._different_entries.items():
            print(f'Кластер {cluster}: ' + ', '.join([f'в таблице {x[0]} - {x[1]}' for x in entries]) + '.')
        print()
        print('Выберите правильную таблицу:')

        hint = f'Введите число от 0 до {self.number_of_fats - 1}'
        while True:
            try:
                table = int(input())
                if table < 0 or table >= self.number_of_fats:
                    print(hint)
                    continue
                break
            except ValueError:
                print(hint)
                continue

        self._default_table = table

    def _determine_free_space_(self):
        """
        Определение свободного пространства на диске.
        """
        free_clusters_count = 0

        for i in range(2, self.data_clusters_count):
            entry = self.read_fat_entry_for_cluster(i, 0)
            if self.is_bad_cluster(entry):
                continue

            entry = int.from_bytes(entry, byteorder='little')
            if i not in self.occupied_clusters and entry:
                self.write_all_fat_entries_for_cluster(i, 0)
            elif entry:
                continue
            free_clusters_count += 1

        self._free_space = free_clusters_count * self.bytes_per_cluster

    def get_file_cluster_chain(self, file):
        """
        Получение цепочки кластеров для объекта файла.
        """
        next_cluster = file.first_cluster
        cluster_chain = []
        while next_cluster:
            cluster_chain.append(next_cluster)
            next_cluster = self.occupied_clusters[next_cluster].next_number
        return cluster_chain

    def _read_directory_(self, directory):
        """
        Получение списка файлов из директории, расположенной в цепочке кластеров.
        """
        files = []
        long_name = []
        no_more_files = False
        for cl in self.get_file_cluster_chain(directory):
            address = self.get_data_address_for_cluster_number(cl)
            self._image_file_handle.seek(address)
            for i in range(self.bytes_per_cluster // 32):
                entry = self._image_file_handle.read(32)
                file = DirectoryEntry(entry)

                if file.name[:1] == bytes.fromhex('00'):
                    no_more_files = True
                    break
                elif file.name[:1] == bytes.fromhex('E5') or file.name[0] == bytes.fromhex('2E'):
                    continue

                directory.number_of_entries += 1
                if file.long_name:
                    file = LongName(entry)
                    long_name.append(file)
                    continue
                elif FileAttribute.volume_id in file.attributes:
                    continue

                if long_name:
                    long_name.reverse()
                    name = bytes.join(b'', [x.name_pt1 + x.name_pt2 + x.name_pt3 for x in long_name])
                    file.name = name.strip(bytes.fromhex('ffff'))
                    file.name = file.name[:-1]
                    file.name_encoding = 'utf-16'
                    long_name = []

                file.parent_offset = i * 32
                file.parent_cluster_number = cl
                files.append(file)

            if no_more_files:
                break

        return files

    def _process_directory_entries_(self, directory, entries):
        """
        Преобразование записей из директории в объекты файлов и директорий.
        """
        files = []

        for entry in entries:
            name = entry.name.decode(entry.name_encoding, errors='ignore').strip().replace('   ', '.')
            if name == '.' or name == '..':
                continue

            if FileAttribute.directory in entry.attributes:
                file = Directory(name, entry.first_cluster_number, entry.attributes, directory,
                                 entry.parent_offset, entry.parent_cluster_number, self.bytes_per_cluster)
            else:
                file = File(name, entry.first_cluster_number, entry.attributes, directory,
                            entry.parent_offset, entry.parent_cluster_number, self.bytes_per_cluster)

            self._set_occupied_clusters_(file)
            files.append(file)
        return files

    def _get_cluster_chain_(self, first_cluster):
        """
        Получение из FAT цепочки всех кластеров файла, начинающегося с данного кластера.
        """
        if first_cluster < 0:
            return [x + first_cluster for x in range(self._root_dir_sectors // self._bs_common.sectors_per_cluster)],\
                   None

        chain = [first_cluster]
        cluster = first_cluster
        while True:
            next_cluster = self.read_fat_entry_for_cluster(cluster, 0)
            next_cluster_number = int.from_bytes(next_cluster, byteorder='little')

            if self.is_end_of_file(next_cluster):
                return chain, None

            if cluster == next_cluster_number:
                return chain, FATError(FATErrorType.self_loop, cluster, next_cluster_number)
            elif next_cluster_number in self.occupied_clusters:
                return chain, FATError(FATErrorType.cluster_intersection, cluster, next_cluster_number)
            elif self.is_bad_cluster(next_cluster) or self.is_reserved_cluster(next_cluster):
                return chain, FATError(FATErrorType.bad_cluster, cluster, next_cluster_number)

            cluster = next_cluster_number
            chain.append(cluster)

    def _change_directory_entries_for_file_(self, new_address, file):
        """
        Изменение адреса файла в содержащей директории.
        """
        parent_cluster_address = self.get_data_address_for_cluster_number(file.parent_cluster_number)
        new_bytes = new_address.to_bytes(length=4, byteorder='little')

        self._journaler.open_transaction(TransactionType.write_cluster)
        self._journaler.report(JournalEvent(file.parent_cluster_number))
        if file.parent:
            self._image_file_handle.seek(parent_cluster_address + file.high_address_offset)
            self._image_file_handle.write(new_bytes[2:])
            self._image_file_handle.seek(parent_cluster_address + file.low_address_offset)
            self._image_file_handle.write(new_bytes[:2])
        elif self.fs_type == FSType.fat32:
            self._image_file_handle.seek(44)
            self._image_file_handle.write(new_bytes)
        else:
            raise RuntimeWarning('Нельзя изменить корневую директорию!')
        self._journaler.close_transaction()

    def _set_occupied_clusters_(self, file):
        """
        Заполнении информации о кластерах, которые содержат файл.
        """
        cluster_chain, fat_error = self._get_cluster_chain_(file.first_cluster)
        file.cluster_count = len(cluster_chain)

        pre_previous = None
        previous = cluster_chain[0]

        for cluster in cluster_chain[1:]:
            self.occupied_clusters[previous] = OccupiedClusterInfo(previous, pre_previous, cluster, file)
            pre_previous = previous
            previous = cluster

        last_info = OccupiedClusterInfo(previous, pre_previous, None, file)
        self.occupied_clusters[previous] = last_info

        if fat_error:
            self._add_error_(fat_error, last_info)

            if fat_error.type == FATErrorType.cluster_intersection:
                second_cluster = self.occupied_clusters[fat_error.next_cluster_number]
                self._add_error_(FATError(FATErrorType.cluster_intersection, second_cluster.number, previous),
                                 second_cluster)

    def _add_error_(self, error, cluster_info):
        """
        Сохранение информации об ошибке для последующего ее исправления.
        """
        if error.cluster_number in self._corrupted_clusters:
            self._corrupted_clusters[error.cluster_number].add(error)
        else:
            self._corrupted_clusters[error.cluster_number] = {error}
        error.cluster_info = cluster_info

    def _file_system_traversal_(self, parent=None):
        """
        Рекурсивный обход всех каталогов файловой системы.
        """
        if parent is None:
            self.occupied_clusters = dict()
            self.directories_count = 0
            self.files_count = 0
            self.root_directory = Directory('', self._root_cluster, [], None, 0, 0, 0)
            self._set_occupied_clusters_(self.root_directory)
            parent = self.root_directory

            if 0 not in self.occupied_clusters:
                self.occupied_clusters[0] = OccupiedClusterInfo(0, None, None, File.get_none_file())

        parent.contents = self._process_directory_entries_(parent, self._read_directory_(parent))
        for file in parent.contents:
            if isinstance(file, Directory):
                self.directories_count += 1
                self._file_system_traversal_(file)
            else:
                self.files_count += 1

    def _correct_errors_(self, remove_corrupted):
        """
        Исправление ошибок с удалением файлов или перемещением их в специальную папку.
        """
        methods = {True: self._remove_file_,
                   False: self._move_file_to_found_}
        self.found_directory = None

        if not self._corrupted_clusters:
            return

        if not remove_corrupted:
            self._create_found_directory_()

        for cluster, errors in self._corrupted_clusters.items():
            for error in errors:
                if error.type == FATErrorType.unclosed_transaction:
                    if error.cluster_number in self.occupied_clusters:
                        error.cluster_info = self.occupied_clusters[error.cluster_number]
                    else:
                        continue
                methods[remove_corrupted](error)

        self._corrupted_clusters = dict()

    def _remove_file_(self, error):
        """
        Удаление поврежденного файла.
        """
        file = error.cluster_info.file

        if file == self.root_directory or File.is_none_file(file):
            return

        self._remove_entries_from_directory_(file)
        for cluster in self.get_file_cluster_chain(file):
            self.write_all_fat_entries_for_cluster(cluster, 0)
            self.occupied_clusters.pop(cluster)
        file.parent.contents.remove(file)

    def _move_file_to_found_(self, error):
        """
        Перемещение поврежденного файла в специальную папку.
        """
        file = error.cluster_info.file

        if file == self.root_directory or file == self.found_directory or File.is_none_file(file):
            return

        is_after = False
        if error.type == FATErrorType.unclosed_transaction:
            error.cluster_info.next_number = None
            for cluster in self.get_file_cluster_chain(file):
                if cluster == error.cluster_number:
                    is_after = True
                    continue

                if is_after:
                    self.occupied_clusters.pop(cluster)
                    self.write_all_fat_entries_for_cluster(cluster, 0)

        if not error.next_cluster_number:
            self._remove_entries_from_directory_(file)
            file.parent.contents.remove(file)
            return

        if file.parent != self.found_directory:
            self._move_file_entries_to_found_(file)

        self.write_all_fat_entries_for_cluster(error.cluster_number, FSType.end_of_file_markers[self.fs_type])

    def _move_file_entries_to_found_(self, file):
        """
        Перемещение записей о файле в специальную папку.
        """
        entries = self._read_entries_from_directory_(file)
        self._remove_entries_from_directory_(file)
        for entry in entries:
            parent_cluster_number, parent_offset = self._add_entry_to_directory(entry, self.found_directory)

        file.parent = self.found_directory
        file.parent_cluster_number = parent_cluster_number
        file.parent_offset = parent_offset
        self.found_directory.contents.append(file)

    def _read_entries_from_directory_(self, file):
        """
        Получение из директории записей о файле.
        """
        start, end = file.get_entries_positions()
        if end > start:
            return self._read_entries_from_directory_cluster_(file.parent_cluster_number, start, end)
        else:
            return self._read_entries_from_directory_cluster_(file.parent_cluster_number, start,
                                                              self.bytes_per_cluster)\
                   + self._read_entries_from_directory_cluster_(file.parent_cluster_number, 0, end)

    def _remove_entries_from_directory_(self, file):
        """
        Удаление из директории записей о файле.
        """
        start, end = file.get_entries_positions()
        if end > start:
            self._remove_entries_from_directory_cluster_(file.parent_cluster_number, start, end)
        else:
            self._remove_entries_from_directory_cluster_(file.parent_cluster_number, start, self.bytes_per_cluster)
            self._remove_entries_from_directory_cluster_(file.parent_cluster_number, 0, end)

    def _read_entries_from_directory_cluster_(self, cluster_number, start, end):
        """
        Получение из кластера директории cluster_number записей о файле между сдвигами run и end.
        """
        address = self.get_data_address_for_cluster_number(cluster_number) + start
        self._image_file_handle.seek(address)
        contents = self._image_file_handle.read(end - start)
        return [contents[i: i + 32] for i in range(0, len(contents), 32) if contents[i: i + 1] != bytes.fromhex('E5')]

    def _remove_entries_from_directory_cluster_(self, cluster_number, start, end):
        """
        Удаление из кластера директории cluster_number записей о файле между сдвигами run и end.
        """
        self._journaler.open_transaction(TransactionType.write_cluster)
        self._journaler.report(JournalEvent(cluster_number))

        address = self.get_data_address_for_cluster_number(cluster_number) + start
        self._image_file_handle.seek(address)
        self._image_file_handle.write(((end - start) // 32) * DirectoryEntry.empty_directory_entry)

        self._journaler.close_transaction()

    def _print_file_system_tree_(self, parent=None, show_hidden_files=True):  # pragma: no cover
        """
        Отображение всех каталогов и файлов файловой системы.
        """
        if parent is None:
            self._directories_depths = {self.root_directory: 0}
            parent = self.root_directory

        content_depth = self._directories_depths[parent] + 1

        for file in parent.contents:
            if not show_hidden_files and FileAttribute.hidden in file.attributes:
                continue

            is_directory = isinstance(file, Directory)
            print('\t' * (content_depth - 1) + file.name + ':' * int(is_directory))
            if is_directory:
                self._directories_depths[file] = content_depth
                self._print_file_system_tree_(file, show_hidden_files)

    def _find_file_(self, file_path):
        """
        Поиск файла по пути.
        """
        file_path = file_path.split('\\')
        if not file_path[0]:
            file_path = file_path[1:]
        index = 0
        file_object = self.root_directory

        while index < len(file_path):
            for file in file_object.contents:
                if file.name == file_path[index]:
                    index += 1
                    file_object = file
                    break
            else:
                return None

        return file_object

    def _get_empty_cluster_(self):
        """
        Поиск свободного кластера на диске.
        """
        for i in range(2, self.data_clusters_count):
            entry = int.from_bytes(self.read_fat_entry_for_cluster(i, 0), byteorder='little')
            if not entry:
                return i
        return -1

    def _add_cluster_(self, file):
        """
        Добавление еще одного кластера в цепочку кластеров файла.
        """
        new_cluster = self._get_empty_cluster_()
        if new_cluster == -1:
            raise RuntimeWarning(f"Невозможно увеличить {file.name}: недостаточно места!")

        self.write_cluster(new_cluster, b'')

        for cluster in self.get_file_cluster_chain(file):
            last_cluster = cluster

        self.occupied_clusters[last_cluster].next_number = new_cluster
        self.occupied_clusters[new_cluster] = OccupiedClusterInfo(new_cluster, last_cluster, None, file)
        file.cluster_count += 1

        self.write_all_fat_entries_for_cluster(last_cluster, new_cluster)
        self.write_all_fat_entries_for_cluster(new_cluster, FSType.end_of_file_markers[self.fs_type])

    def _add_entry_to_directory(self, entry, directory):
        """
        Добавление новой записи в директорию.
        """
        offset = directory.number_of_entries
        parent_cluster_index = offset // (self.bytes_per_cluster // 32)
        parent_offset = offset % (self.bytes_per_cluster // 32)

        if parent_cluster_index > directory.cluster_count - 1:
            self._add_cluster_(directory)

        i = 0
        for number in self.get_file_cluster_chain(directory):
            if i > parent_cluster_index:
                break
            parent_cluster_number = number
            i += 1

        self._journaler.open_transaction(TransactionType.write_cluster)
        self._journaler.report(JournalEvent(parent_cluster_number))

        address = self.get_data_address_for_cluster_number(parent_cluster_number) + offset * 32
        self._image_file_handle.seek(address)
        self._image_file_handle.write(entry)

        self._journaler.close_transaction()
        directory.number_of_entries += 1

        return parent_cluster_number, parent_offset * 32

    def _prepare_clusters_(self, name, parent, is_directory=True, contents=b''):
        """
        Подготовка и заполнение кластеров для создания файла name в директории parent.
        """
        for file in parent.contents:
            if file.name == name:
                raise ValueError("Файл с таким именем уже существует!")

        cluster_count = len(contents) // self.bytes_per_cluster + 1
        clusters = []
        for i in range(cluster_count):
            cl = self._get_empty_cluster_()
            if cl == -1:
                for j in clusters:
                    self.write_all_fat_entries_for_cluster(j, 0)

                raise RuntimeWarning("Невозможно создать файл: недостаточно места!")

            clusters.append(cl)
            self.write_all_fat_entries_for_cluster(clusters[i], FSType.end_of_file_markers[self.fs_type])
            if i > 0:
                self.write_all_fat_entries_for_cluster(clusters[i - 1], clusters[i])

        self.write_all_fat_entries_for_cluster(clusters[-1], FSType.end_of_file_markers[self.fs_type])

        first_cluster = clusters[0]
        entry = DirectoryEntry.create_short_directory_entry(name, first_cluster, is_directory, len(contents))

        for i in range(cluster_count):
            self.write_cluster(clusters[i], contents[i * self.bytes_per_cluster: (i + 1) * self.bytes_per_cluster])

        parent_cluster_number, parent_offset = self._add_entry_to_directory(entry, parent)
        return parent_cluster_number, parent_offset, clusters

    def create_directory(self, name, parent):
        """
        Создание директории с именем name в папке parent.
        """
        parent_cluster_number, parent_offset, clusters = self._prepare_clusters_(name, parent)
        first_cluster = clusters[0]
        directory = Directory(name, first_cluster, (FileAttribute.directory,), parent, parent_offset,
                              parent_cluster_number, self.bytes_per_cluster)
        directory.cluster_count = len(clusters)
        parent.contents.append(directory)
        self._set_occupied_clusters_(directory)
        return directory

    def create_file(self, name, parent, contents):
        """
        Создание файла с именем name и содержимым contents в папке parent.
        """
        parent_cluster_number, parent_offset, clusters = self._prepare_clusters_(name, parent, False, contents)
        first_cluster = clusters[0]
        file = File(name, first_cluster, (), parent, parent_offset, parent_cluster_number, self.bytes_per_cluster)
        file.cluster_count = len(clusters)
        parent.contents.append(file)
        self._set_occupied_clusters_(file)
        return file

    def _create_found_directory_(self):
        """
        Создание директории для поврежденных файлов.
        """
        name = 'FOUND'
        tail = ''
        while True:
            try:
                self.found_directory = self.create_directory(name + tail, self.root_directory)
                break
            except ValueError:
                tail = str(randint(1, 10 ** 3))
                continue
        self.directories_count += 1

    def print_information(self):  # pragma: no cover
        """
        Отображение основной информации о файловой системе.
        """
        print(f'''Файловая система: {FSType.type_string[self.fs_type]}
Количество таблиц: {self._bs_common.number_of_fats}
Количество файлов: {self.files_count}
Количество директорий: {self.directories_count}
Количество секторов: {self.data_clusters_count * self._bs_common.sectors_per_cluster}

Емкость: {self._disk_capacity} байт
Занято: {self._disk_capacity - self._free_space} байт\t\tСвободно: {self._free_space} байт''')

    def print_contents(self, show_hidden_files=True):  # pragma: no cover
        """
        Отображение всех каталогов и их содержимого, включая или не включая скрытые файлы.
        """
        print('Содержимое:\n')
        self._print_file_system_tree_(show_hidden_files=show_hidden_files)

    def __del__(self):
        self._image_file_handle.close()


def __create_parser__():  # pragma: no cover
    arg_parser = argparse.ArgumentParser(add_help=False)

    arg_parser.add_argument('-h', '--help', action='store_true')
    arg_parser.add_argument('-f', '--file', action='store')
    arg_parser.add_argument('-j', '--journal_file', action='store')
    arg_parser.add_argument('-i', '--info', action='store_true')
    arg_parser.add_argument('-c', '--contents', action='store_true')
    arg_parser.add_argument('-s', '--show_hidden', action='store_true')
    arg_parser.add_argument('-_mode', '--remove_corrupted', action='store_true')
    arg_parser.add_argument('-d', '--default_table', action='store')
    arg_parser.add_argument('-g', '--get_file', action='store')

    return arg_parser


def __help__():  # pragma: no cover
    print('''Обработчик образа диска.
    
Использование:
python file_system_processor.py --help
python file_system_processor.py -f <Образ диска> -g <Путь к файлу>
python file_system_processor.py -f <Образ диска> -i
python file_system_processor.py -f <Образ диска> -c
python file_system_processor.py -f <Образ диска> -c -s
python file_system_processor.py -f <Образ диска> -i -c


Ключи:
-h, --help - вывод справки
-f, --file - файл образа диска для анализа
-j, --journal_file - имя файла журнала
-i, --info - посмотреть информацию о файловой системе
-c, --contents - посмотреть содержимое диска
-s, --show_hidden - отобразить скрытые файлы и папки
-_mode, --remove_corrupted - удалить поврежденные файлы (по умолчанию помещаются в специальную папку)
-d, --default_table - значение таблицы по умолчанию, если записи в разных таблицах не совпадают
-g, --get_file - сохранить файл из образа (формат пути к файлу: \\folder\\folder\\file)
''')


def main(arguments):  # pragma: no cover
    fs_processor = FileSystemProcessor(arguments.file, arguments.remove_corrupted,
                                       arguments.default_table, arguments.journal_file)
    if arguments.info:
        fs_processor.print_information()

    if arguments.contents:
        fs_processor.print_contents(show_hidden_files=arguments.show_hidden)

    if arguments.get_file:
        fl = list(fs_processor.get_file(arguments.get_file))
        fl_name = arguments.get_file.split('\\')[-1]

        if not fl:
            print('Файл не найден!')

        with open(fl_name, 'wb') as f:
            for piece in fl:
                f.write(piece)


if __name__ == '__main__':  # pragma: no cover
    parser = __create_parser__()
    args = parser.parse_args()

    if args.help or not args.file:
        __help__()
        exit()

    main(args)
