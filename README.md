# Defrag
FAT* defragmentation

## Требования
* Python версии не ниже 3.6
* Модуль bitstring

## Рекомендации по запуску
Каждый модуль можно запустить самостоятельно, но лучше начинать с `main.py`.
Справка по ключу `--help`.

Например, можно запустить так:

`python main.py -f _sample_fat16.vhd -m INFO -i`

`python main.py -f _sample_fat16.vhd -m INFO -c -s`

`python main.py -f _sample_fat16.vhd -m INFO -d 0 -c -s -r`

`python main.py -f _sample_fat16.vhd -m FRAG`

`python main.py -f _sample_fat16.vhd -m DEFRAG -de`

`python main.py -f _sample_fat16.vhd -m ERROR -o`

`python main.py -f _sample_fat16.vhd -m ERROR -b -sl -in`

## Подробности реализации
Все основные модули находятся в папке `defrag\`.
Класс `file_system_processor.FileSystemProcessor` представляет собой абстракцию файловой системы. 
В своей работе он использует вспомогательные файлы из модуля `service_classes.py`.
Для обеспечения восстановления при принудительном завершении работы ведется журналирование 
с помощью `journaler.Journaler`.

Классы `defragmentator.Defragmentator`, `fragmentator.Fragmentator` и `error_creator.ErrorCreator`
используют для своей работы абстракцию из `file_system_processor.FileSystemProcessor`.

На данные модули (`file_system_processor`, `defragmentator`, `fragmentator`, `error_creator`,
`journaler.py`, `service_classes`) написаны тесты, их можно найти в `tests\test_defrag.py`.

**Для запуска тестов необходимо в папку с ними добавить образы для тестирования, скачать их можно тут: https://vk.cc/8JDrBT**
Образы для тестирования заканчиваются на .test, два других можно использовать по своему усмотрению.

Покрытие по строкам составляет около 91%:

    file_system_processor.py        567       92      84%   
    error_creator.py                 60        2      97%   
    defragmentator.py                49        8      84%   
    fragmentator.py                  37        5      86%   
    error_creator.py                 43        0     100%   
    service_classes.py              172        2      99%   
