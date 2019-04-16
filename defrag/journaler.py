#!/usr/bin/env python3
"""
Журналирование обработчика образа диска для восстановления после отключения питания.
"""

from os import path
from json import dumps
from json import loads


class Journaler:
    """
    Создатель журнала.
    """
    _default_filename = "fat_journal.log"

    def __init__(self, image_filename, journal_filename=None):
        self._image_filename = image_filename
        self.unclosed_transactions = None

        if journal_filename:
            self._filename = journal_filename
        else:
            self._filename = self._default_filename

        if path.isfile(self._filename):
            self._handle = open(self._filename, '_mode')
            self._recover_data_()
        else:
            self._handle = open(self._filename, 'w')

        self._add_capture_(image_filename)

    def _recover_data_(self):
        """
        Восстановление из журнала данных после принудительного завершения.
        """
        first_line = True
        transaction_stack = []

        for line in self._handle:
            line = line.strip('\n')
            if first_line and line != self._image_filename:
                first_line = False
                break
            elif first_line:
                first_line = False
                continue

            if line.find('TRANSACTION') != -1:
                transaction_stack.append([int(line.split()[1])])
            elif line.find('CLOSED') != -1:
                transaction_stack.pop()
            else:
                transaction_stack[-1].append(JournalEvent.from_json(line))

        self.unclosed_transactions = transaction_stack if transaction_stack else None
        self._handle.close()
        self._handle = open(self._filename, 'w')

    def _add_capture_(self, capture):
        """
        Добавление в журнал подписи.
        """
        self._handle.write(capture + '\n')

    def open_transaction(self, transaction_type):
        """
        Открытие транзакции.
        """
        self._handle.write(f'TRANSACTION {transaction_type}\n')

    def report(self, event):
        """
        Запись события в журнал.
        """
        self._handle.write(event.json + '\n')

    def close_transaction(self):
        """
        Закрытие транзакции.
        """
        self._handle.write('CLOSED\n')

    def __del__(self):
        self._handle.close()


class TransactionType:
    """
    Тип транзакции.
    """
    write_table = 0
    write_cluster = 1
    write_both = 2


class JournalEvent:
    """
    Абстракция записи в журнале.
    """
    def __init__(self, cluster_number, value=None, table=None):
        self.cluster_number = cluster_number
        self.value = value
        self.table = table

    @property
    def json(self):
        """
        Приведение записи в формат json для записи в файл.
        """
        return dumps(self.__dict__)

    @classmethod
    def from_json(cls, line):
        """
        Загрузка объекта записи из json-строки.
        """
        fields = loads(line)
        return JournalEvent(fields['cluster_number'], fields['value'], fields['table'])


if __name__ == '__main__':  # pragma: no cover
    print('''Это служебный файл.
Запустите file_system_processor.py, error_creator.py, fragmentator.py или defragmentator.py!''')
    exit()

