#!/usr/bin/env python3
"""
Точка входа.
"""

import sys
import argparse


def __create_parser__():  # pragma: no cover
    arg_parser = argparse.ArgumentParser(add_help=False)

    arg_parser.add_argument('-h', '--help', action='store_true')
    arg_parser.add_argument('-f', '--file', action='store')
    arg_parser.add_argument('-j', '--journal_file', action='store')
    arg_parser.add_argument('-m', '--mode', action='store')

    arg_parser.add_argument('-i', '--info', action='store_true')
    arg_parser.add_argument('-c', '--contents', action='store_true')
    arg_parser.add_argument('-s', '--show_hidden', action='store_true')
    arg_parser.add_argument('-_mode', '--remove_corrupted', action='store_true')
    arg_parser.add_argument('-d', '--default_table', action='store')
    arg_parser.add_argument('-g', '--get_file', action='store')

    arg_parser.add_argument('-l', '--level', action='store_true')
    arg_parser.add_argument('-de', '--defragmentation', action='store_true')

    arg_parser.add_argument('-o', '--one_table', action='store_true')
    arg_parser.add_argument('-b', '--bad_cluster', action='store_true')
    arg_parser.add_argument('-se', '--self_loop', action='store_true')
    arg_parser.add_argument('-in', '--intersection', action='store_true')

    return arg_parser


def __help__():  # pragma: no cover
    print('''\tОбработчик образа диска, его фрагментация, дефрагментация и внесение ошибок.

\tИспользование:
python main.py --help
python main.py -f <Образ диска> -m <Режим работы>

\tПримеры запуска:
python main.py -f _sample_fat16.vhd -m INFO -i
python main.py -f _sample_fat16.vhd -m INFO -c -s
python main.py -f _sample_fat16.vhd -m INFO -d 0 -c -s -_mode
python main.py -f _sample_fat16.vhd -m FRAG
python main.py -f _sample_fat16.vhd -m DEFRAG -de
python main.py -f _sample_fat16.vhd -m ERROR -o
python main.py -f _sample_fat16.vhd -m ERROR -b -sl -in


\tКлючи (общие для всех режимов):
-h, --help - вывод справки
-f, --file - файл образа диска для анализа
-j, --journal_file - имя файла журнала
-m, --mode - режим работы

Режимы работы: INFO, FRAG, DEFRAG, ERROR.

\tРежим INFO (обработчик образа диска):
-i, --info - посмотреть информацию о файловой системе
-c, --contents - посмотреть содержимое диска
-s, --show_hidden - отобразить скрытые файлы и папки
-_mode, --remove_corrupted - удалить поврежденные файлы (по умолчанию помещаются в специальную папку)
-d, --default_table - значение таблицы по умолчанию, если записи в разных таблицах не совпадают
-g, --get_file - сохранить файл из образа (формат пути к файлу: \\folder\\folder\\file)

\tРежим FRAG (фрагментация образа диска).

\tРежим DEFRAG (дефрагментация образа диска):
-l, --level - посмотреть уровень фраментации диска
-de, --defragmentation - запустить дефрагментацию

\tРежим ERROR (внесение ошибок):
-o, --one_table - созданиена на образе диска файла с записью только в одну таблицу
-b, --bad_cluster - созданиена на образе диска файла с поврежденным кластером в цепочке
-sl, --self_loop - созданиена на образе диска файла с зацикливанием цепочки
-in, --intersection - созданиена на образе диска двух пересекающихся файлов
''')


def main():  # pragma: no cover
    if sys.version_info < (3, 6):
        print("Требуется Python версии не ниже 3.6!", file=sys.stderr)
        sys.exit(1)

    from defrag.file_system_processor import main as fs_main
    from defrag.fragmentator import main as fr_main
    from defrag.defragmentator import main as de_main
    from defrag.error_creator import main as er_main

    methods = {'INFO': fs_main,
               'FRAG': fr_main,
               'DEFRAG': de_main,
               'ERROR': er_main}

    parser = __create_parser__()
    args = parser.parse_args()

    if args.help or not (args.file and args.mode):
        __help__()
        exit()

    methods[args.mode](args)


if __name__ == '__main__':  # pragma: no cover
    main()
