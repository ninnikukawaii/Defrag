#!/usr/bin/env python3
"""
Дефрагментация образа диска.
"""

import argparse
from service_classes import File
from file_system_processor import FileSystemProcessor


class Defragmentator:
    """
    Дефрагментатор.
    """
    def __init__(self, image_file, journal_file=None):
        self._file_system = FileSystemProcessor(image_file, journal_file=journal_file)
        self._files = set(map(lambda x: x.file, self._file_system.occupied_clusters.values()))
        self._files.remove(self._file_system.root_directory)

        none_file = None
        for file in self._files:
            if File.is_none_file(file):
                none_file = file

        if none_file:
            self._files.remove(none_file)

    def calculate_fragmentation_level(self):
        """
        Вычисление уровня фрагментации диска.
        """
        misplaced_clusters = 0
        for file in self._files:
            for cluster in self._file_system.get_file_cluster_chain(file):
                previous = self._file_system.occupied_clusters[cluster].previous_number
                if not previous:
                    break
                misplaced_clusters += int(cluster != previous + 1)

        return misplaced_clusters * 100 / len(self._file_system.occupied_clusters.keys())

    def defragmentation(self):
        """
        Дефрагментация файловой системы.
        """
        files = sorted(self._files, key=lambda x: x.first_cluster)

        for file in files:
            self._order_file_clusters_(file)

    def _order_file_clusters_(self, file):
        """
        Упорядочивание кластеров файла.
        """
        for cluster in self._file_system.get_file_cluster_chain(file):
            cluster_entry = self._file_system.occupied_clusters[cluster]
            if not cluster_entry.previous_number:
                continue

            new_position = cluster_entry.previous_number + 1
            attempts = 5
            while cluster_entry.number != new_position and attempts:
                if new_position > self._file_system.data_clusters_count:
                    return

                new_cluster_entry = self._file_system.read_fat_entry_for_cluster(new_position, 0)
                if self._file_system.is_bad_cluster(new_cluster_entry) or \
                        self._file_system.is_reserved_cluster(new_cluster_entry):
                    new_position += 1
                    attempts -= 1
                    continue
                try:
                    self._file_system.swap_clusters(cluster, new_position)
                except ValueError:
                    break

    def print_fragmentation_level(self):
        """
        Отображение уровня фрагментации диска.
        """
        print(f'Уровень фрагментации диска: {round(self.calculate_fragmentation_level(), 1)}%')


def __create_parser__():  # pragma: no cover
    arg_parser = argparse.ArgumentParser(add_help=False)

    arg_parser.add_argument('-h', '--help', action='store_true')
    arg_parser.add_argument('-f', '--file', action='store')
    arg_parser.add_argument('-l', '--level', action='store_true')
    arg_parser.add_argument('-de', '--defragmentation', action='store_true')

    return arg_parser


def __help__():  # pragma: no cover
    print('''Дефрагментация образа диска.

Использование:
python defragmentator.py --help
python defragmentator.py -f <Образ диска> -d
python defragmentator.py -f <Образ диска> -l


Ключи:
-h, --help - вывод справки
-f, --file - файл образа диска для дефрагментации
-l, --level - посмотреть уровень фраментации диска
-de, --defragmentation - запустить дефрагментацию
''')


def main(arguments):  # pragma: no cover
    defragmentator = Defragmentator(arguments.file)
    if arguments.level:
        defragmentator.print_fragmentation_level()

    if arguments.defragmentation:
        defragmentator.defragmentation()


if __name__ == '__main__':  # pragma: no cover
    parser = __create_parser__()
    args = parser.parse_args()

    if args.help or not args.file:
        __help__()
        exit()

    main(args)
