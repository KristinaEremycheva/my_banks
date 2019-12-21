# -*- coding: cp1251 -*-
# -*- coding: UTF-8 -*-
# для HTTP-запросов
import requests
# для парсинга XML (реестра банков)
import xml.etree.ElementTree as ET
# для импорта json
import json
# для получения аргументов командной строки и выхода из программы в случае ошибки
import sys
# для проверки существования файлов
import os
# для реализации задержки при обращении к ЕГРЮЛ
import time
# индикатор прогресса
from tqdm import tqdm



# имя файла, в который мы будем сохранять реестр банков
bank_registry_file = "bank_registry.xml"
# имя файла с информацией по банку: название, ИНН
banks_info_file = "bank_info.tsv"

# если файл с реестром банков присутствует в текущей папке, загружает из него реестр
# если файл отсутствует, загружает реестр банков с сайта ЦБР, сохраняет его в файл
def get_bank_registry(filename):
    # URL, откуда качать реестр банков
    bank_registry_url = "http://www.cbr.ru/scripts/XML_bic2.asp"

    # качаем реестр банков, если его нет в текущей папке
    if not os.path.isfile(filename):
        print("%s: скачиваем реестр банков..." % sys.argv[0])
        response = requests.get(bank_registry_url)
        if response.status_code == 200 and "application/xml" in response.headers["content-type"]:
            with open(bank_registry_file, "wb") as br:
                br.write(response.content)
        else:
            print("%s: не удалось загрузить реестр банков." % sys.argv[0])
            sys.exit(2)

    # парсим xml
    with open(filename, "rb") as xml:
        xml_tree = ET.parse(xml)
        xml_root = xml_tree.getroot()

    banks = []
    for xml_bank in xml_root:
        bank = {}
        for xml_field in xml_bank:
            bank[xml_field.tag] = xml_field.text;
        banks.append(bank)

    print("%s: количество банков в реестре: %d." % (sys.argv[0], len(banks)))

    return banks

# получает ИНН организации поиском ОГРН по базе ЕГРЮЛ
def get_inn(ogrn):
    inn = ""
    if ogrn is None:
        return inn

    # инициализируем сессию
    s = requests.Session()
    res = s.get("https://egrul.nalog.ru/index.html")

    # поисковый запрос к ЕГРЮЛ
    res = s.post("https://egrul.nalog.ru",
            data={ "vyp3CaptchaToken": "", "page": "", "query": ogrn, "region": "", "PreventChromeAutocomplete": ""})

    ans = json.loads(res.text)

    if "ERRORS" in ans:
        print(ans)
        return inn

    # параметр для второго запроса
    t = ans["t"]

    # будем запрашивать результаты, пока не получим их
    # !TODO: сделать ограничение на количество попыток запроса
    while True:
        # второй запрос
        res = s.get("https://egrul.nalog.ru/search-result/"+t)
        ans = json.loads(res.text)

        # сервер может не выдать данные сразу, вернув статус "wait", повторяем запрос через 5 секунд
        if "status" in ans and ans["status"] == "wait":
            time.sleep(5)
        else:
            found = json.loads(res.text)["rows"]
            inn = found[0]["i"]
            break

    # возвращаем инн первой найденной организации
    return inn

# загружает файл с названиями банков и ИНН
def get_banks_info(bank_registry, filename):
    banks = []

    if not os.path.isfile(banks_info_file):
        print("%s: получаем ИНН банков из ЕГРЮЛ..." % sys.argv[0])
        with open(banks_info_file, "w") as bi:
            for i in tqdm(range(len(bank_registry))):
                # получаем ИНН
                inn = get_inn(bank_registry[i]["RegNum"])
                bi.write(("%s\t%s\n" % (bank_registry[i]["ShortName"], inn)))
                # задержка, чтобы ограничить нагрузку на сервер (если генерировать слишком много запросов,
                # он может включить капчу)
                time.sleep(1)

    # читаем файл в список строк
    with open(filename, "r") as f:
        lines = f.readlines()

    # поля в файле разделены табуляцией
    for l in lines:
        fields = l.split("\t")
        banks.append({"name": fields[0], "inn": fields[1].rstrip()})

    # убираем из списка банки, у которых нет ИНН
    banks = list(filter(lambda x: x["inn"] != "", banks))
    print("%s: количество банков в реестре с известным ИНН: %d." % (sys.argv[0], len(banks)))

    return banks

# загружает контракты за указанный период для указанного поставщика услуг (согласно ИНН)
def get_contracts(start_date, stop_date, inn):
    contracts = []

    # конструируем запрос
    url = 'http://openapi.clearspending.ru/restapi/v3/contracts/select/?'
    # период
    url += "&daterange=%s-%s" % (start_date, stop_date)
    # ИНН поставщика услуг (банка)
    url += "&supplierinn=%s" % inn
    # федеральный закон
    url += "&fz=44"

    res = requests.get(url)
    num_pages = 0
    try:
        ans = json.loads(res.text)
        if "contracts" in ans:
            # количество контрактов
            num_contracts = ans["contracts"]["total"]
            # количество страниц в ответе
            num_pages = int(num_contracts/50) + (num_contracts % 50 != 0)
    except ValueError:
        pass

    # загружаем контракты со всех страниц в ответе
    for page in range(1, num_pages+1):
        target = url + ("&page=%s" % page)
        res = requests.get(target)
        contracts += json.loads(res.text)["contracts"]["data"]

    return contracts

if (len(sys.argv) != 3):
    print("Usage: %s <начало периода ДД.ММ.ГГГГ> <конец периода ДД.ММ.ГГГГ>" % sys.argv[0])
    sys.exit(1)


# загружаем контракты для всех банков за указанный период
def get_all_contracts(banks_info, start_date, stop_date):
    all_contracts = []

    # имя файла с информацией по контрактам за указанный период
    contracts_info_file = "contracts_info_%s_%s.json" % (start_date, stop_date)

    # проверяем, не загружен ли у нас уже список контрактов
    if not os.path.isfile(contracts_info_file):

        if not os.path.isfile(contracts_info_file):
            print("%s: загружаем контракты для каждого банка из списка..." % sys.argv[0])
            # загружаем контракты для каждого ИНН
            for i in tqdm(range(len(banks_info))):
                bank_contracts = get_contracts(start_date=sys.argv[1], stop_date=sys.argv[2], inn=banks_info[i]["inn"])
                all_contracts.append({"name": banks_info[i]["name"], "inn": banks_info[i]["inn"], "contracts": bank_contracts})

            with open(contracts_info_file, "w") as f:
                json.dump(all_contracts, f)

    with open(contracts_info_file) as f:
        data = json.loads(f.readline())

    return data


# загружаем реестр банков
bank_registry = get_bank_registry(bank_registry_file)
# загружаем ИНН банков
banks_info = get_banks_info(bank_registry, banks_info_file)
# загрузаем список контрактов
all_contracts = get_all_contracts(banks_info, sys.argv[1], sys.argv[2])

# считаем полную сумму контрактов по каждому банку
banks = []
print("%s: обрабатывается список контрактов..." % sys.argv[0])
for i in range(len(all_contracts)):
    pricesum = 0
    for c in all_contracts[i]["contracts"]:
        pricesum += c["price"]
    banks.append({"name": all_contracts[i]["name"], "sum": pricesum, "num": len(all_contracts[i]["contracts"])})

# убираем из списка банки, с которыми не были заключены контракты
banks = list(filter(lambda x: x["sum"] != 0, banks))
# сортируем банки по сумме заключенных контрактов
banks = sorted(banks, key=lambda x: x["sum"], reverse=True)

# для более красивого вывода определяем размеры полей
max_name_len = len(max(banks, key=lambda x: len(x["name"]))["name"])
max_sum_len = len("%.2f" % max(banks, key=lambda x: len("%.2f" % x["sum"]))["sum"])
max_num_len = len("%d" % (max(banks, key=lambda x: len("%d" % x["num"])))["num"])
# выводим список банков
for i in range(len(banks)):
    # выводим информацию в две колонки: название банка и сумма заключенных контрактов
    # используем функцию format для выравнивания
    print(("{:<%d} {:>%d} {:>%d}" % (max_name_len, max_num_len, max_sum_len)).format(banks[i]["name"], "%d" % banks[i]["num"], "%.2f" % banks[i]["sum"]))

#Визуализация ТОП-10 банков
import matplotlib.pyplot as plt

#вызов диаграммы нужного типа
plt.rcdefaults()
fig, ax = plt.subplots()

top_num = 10
names = list(map(lambda x: x['name'], banks[:top_num]))#принимает список банков и берет первые 10
y_pos = range(top_num)
sums = list(map(lambda x: x['sum'], banks[:top_num]))

ax.barh(y_pos, sums)#построение горизонтальной диаграммы
ax.set_yticks(y_pos)
ax.set_yticklabels(names)#набор меток
ax.invert_yaxis() # labels читаются сверху вниз
ax.set_xlabel('Сумма контрактов')#ось абцисс
ax.set_title('ТОП банков по сумме контрактов')#заголовок
plt.show()#вывод изображения на экран



