#!/usr/bin/env python3
"""
Скрипт внесения ошибок в образ диска.
"""

import argparse
from random import randint
from service_classes import FSType
from file_system_processor import FileSystemProcessor


class ErrorCreator:
    """
    Создатель ошибок.
    """

    _filename = 'FILE'

    def __init__(self, image_file, print_info=False, journal_file=None):
        self._file_system = FileSystemProcessor(image_file, journal_file=journal_file)
        self._print_info = print_info

    def create_file_in_only_one_table(self, fat_number):
        """
        Создание файла и помещение записи о нем только в одну таблицу fat_number.
        """
        file = self._create_file_()
        tables = [i for i in range(self._file_system.number_of_fats) if i != fat_number]
        for cluster in self._file_system.get_file_cluster_chain(file):
            for table in tables:
                self._file_system.write_fat_entry_for_cluster(cluster, 0, table)

        if self._print_info:  # pragma: no cover
            print(f'Создан файл {file.name} с записью только в таблице {fat_number}.')

        return file

    def create_file_with_bad_cluster(self):
        """
        Создание файла с поврежденным кластером в цепочке.
        """
        file = self._create_file_()
        cluster_number = self._file_system.occupied_clusters[file.first_cluster].next_number
        self._file_system.write_all_fat_entries_for_cluster(cluster_number,
                                                            FSType.bad_cluster_markers[self._file_system.fs_type])

        if self._print_info:  # pragma: no cover
            print(f'Создан файл {file.name} с поврежденным кластером {cluster_number}.')

        return file

    def create_file_with_self_loop(self):
        """
        Создане файла с зацикливанием цепочки.
        """
        file = self._create_file_()
        cluster_number = file.first_cluster
        self._file_system.write_all_fat_entries_for_cluster(cluster_number, cluster_number)

        if self._print_info:  # pragma: no cover
            print(f'Создан файл {file.name} зацикливащийся в кластере {cluster_number}.')

        return file

    def create_intersecting_files(self):
        """
        Создание пересекающихся файлов.
        """
        first_file = self._create_file_(3)
        first_cluster = self._file_system.occupied_clusters[first_file.first_cluster].next_number
        second_file = self._create_file_(3)
        second_cluster = self._file_system.occupied_clusters[second_file.first_cluster].next_number
        self._file_system.write_all_fat_entries_for_cluster(first_cluster, second_cluster)

        if self._print_info:  # pragma: no cover
            print(f'Созданы файлы {first_file.name} и {second_file.name} пересекающиеся в кластере {second_cluster}.')

        return first_file, second_file

    def _create_file_(self, length=2):
        """
        Создание файла длины length.
        """
        tail = ''
        while True:
            try:
                file = self._file_system.create_file(self._filename + tail, self._file_system.root_directory,
                                                     b'e' * self._file_system.bytes_per_cluster * length)
                break
            except ValueError:
                tail = str(randint(0, 10 ** 4))
        return file


def __create_parser__():  # pragma: no cover
    arg_parser = argparse.ArgumentParser(add_help=False)

    arg_parser.add_argument('-h', '--help', action='store_true')
    arg_parser.add_argument('-f', '--file', action='store')
    arg_parser.add_argument('-o', '--one_table', action='store_true')
    arg_parser.add_argument('-b', '--bad_cluster', action='store_true')
    arg_parser.add_argument('-se', '--self_loop', action='store_true')
    arg_parser.add_argument('-in', '--intersection', action='store_true')

    return arg_parser


def __help__():  # pragma: no cover
    print('''Дефрагментация образа диска.

Использование:
python error_creator.py --help
python error_creator.py -f <Образ диска> -o
python error_creator.py -f <Образ диска> -b
python error_creator.py -f <Образ диска> -s -i


Ключи:
-h, --help - вывод справки
-f, --file - файл образа диска для дефрагментации
-o, --one_table - созданиена на образе диска файла с записью только в одну таблицу
-b, --bad_cluster - созданиена на образе диска файла с поврежденным кластером в цепочке
-se, --self_loop - созданиена на образе диска файла с зацикливанием цепочки
-in, --intersection - созданиена на образе диска двух пересекающихся файлов
''')


def main(arguments):  # pragma: no cover
    error_creator = ErrorCreator(arguments.file, True)

    if arguments.one_table:
        error_creator.create_file_in_only_one_table(0)
    if arguments.bad_cluster:
        error_creator.create_file_with_bad_cluster()
    if arguments.self_loop:
        error_creator.create_file_with_self_loop()
    if arguments.intersection:
        error_creator.create_intersecting_files()


if __name__ == '__main__':  # pragma: no cover
    parser = __create_parser__()
    args = parser.parse_args()

    if args.help or not args.file:
        __help__()
        exit()

    main(args)
