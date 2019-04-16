#!/usr/bin/env python3
"""
Фрагментация образа диска.
"""

import argparse
from random import randint
from service_classes import File
from file_system_processor import FileSystemProcessor


class Fragmentator:
    """
    Фрагментатор.
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

    def fragmentation(self):
        """
        Фрагментация файловой системы.
        """
        files = sorted(self._files, key=lambda x: x.first_cluster)

        for file in files:
            self._misplace_file_clusters_(file)

    def _misplace_file_clusters_(self, file):
        """
        Нарушение порядка кластеров файла.
        """
        for cluster in self._file_system.get_file_cluster_chain(file):
            cluster_entry = self._file_system.occupied_clusters[cluster]

            if not cluster_entry.previous_number:
                continue

            new_position = randint(file.first_cluster, self._file_system.data_clusters_count - 15)
            attempts = 5
            while cluster_entry.number == cluster_entry.previous_number + 1 and attempts:
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


def __create_parser__():  # pragma: no cover
    arg_parser = argparse.ArgumentParser(add_help=False)

    arg_parser.add_argument('-h', '--help', action='store_true')
    arg_parser.add_argument('-f', '--file', action='store')

    return arg_parser


def __help__():  # pragma: no cover
    print('''Фрагментация образа диска.

Использование:
python fragmentator.py --help
python fragmentator.py -f <Образ диска>


Ключи:
-h, --help - вывод справки
-f, --file - файл образа диска для фрагментации
''')


def main(arguments):  # pragma: no cover
    fragmentator = Fragmentator(arguments.file)
    fragmentator.fragmentation()


if __name__ == '__main__':  # pragma: no cover
    parser = __create_parser__()
    args = parser.parse_args()

    if args.help or not args.file:
        __help__()
        exit()

    main(args)
