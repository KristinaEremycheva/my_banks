# -*- coding: cp1251 -*-
# -*- coding: UTF-8 -*-
# ��� HTTP-��������
import requests
# ��� �������� XML (������� ������)
import xml.etree.ElementTree as ET
# ��� ������� json
import json
# ��� ��������� ���������� ��������� ������ � ������ �� ��������� � ������ ������
import sys
# ��� �������� ������������� ������
import os
# ��� ���������� �������� ��� ��������� � �����
import time
# ��������� ���������
from tqdm import tqdm



# ��� �����, � ������� �� ����� ��������� ������ ������
bank_registry_file = "bank_registry.xml"
# ��� ����� � ����������� �� �����: ��������, ���
banks_info_file = "bank_info.tsv"

# ���� ���� � �������� ������ ������������ � ������� �����, ��������� �� ���� ������
# ���� ���� �����������, ��������� ������ ������ � ����� ���, ��������� ��� � ����
def get_bank_registry(filename):
    # URL, ������ ������ ������ ������
    bank_registry_url = "http://www.cbr.ru/scripts/XML_bic2.asp"

    # ������ ������ ������, ���� ��� ��� � ������� �����
    if not os.path.isfile(filename):
        print("%s: ��������� ������ ������..." % sys.argv[0])
        response = requests.get(bank_registry_url)
        if response.status_code == 200 and "application/xml" in response.headers["content-type"]:
            with open(bank_registry_file, "wb") as br:
                br.write(response.content)
        else:
            print("%s: �� ������� ��������� ������ ������." % sys.argv[0])
            sys.exit(2)

    # ������ xml
    with open(filename, "rb") as xml:
        xml_tree = ET.parse(xml)
        xml_root = xml_tree.getroot()

    banks = []
    for xml_bank in xml_root:
        bank = {}
        for xml_field in xml_bank:
            bank[xml_field.tag] = xml_field.text;
        banks.append(bank)

    print("%s: ���������� ������ � �������: %d." % (sys.argv[0], len(banks)))

    return banks

# �������� ��� ����������� ������� ���� �� ���� �����
def get_inn(ogrn):
    inn = ""
    if ogrn is None:
        return inn

    # �������������� ������
    s = requests.Session()
    res = s.get("https://egrul.nalog.ru/index.html")

    # ��������� ������ � �����
    res = s.post("https://egrul.nalog.ru",
            data={ "vyp3CaptchaToken": "", "page": "", "query": ogrn, "region": "", "PreventChromeAutocomplete": ""})

    ans = json.loads(res.text)

    if "ERRORS" in ans:
        print(ans)
        return inn

    # �������� ��� ������� �������
    t = ans["t"]

    # ����� ����������� ����������, ���� �� ������� ��
    # !TODO: ������� ����������� �� ���������� ������� �������
    while True:
        # ������ ������
        res = s.get("https://egrul.nalog.ru/search-result/"+t)
        ans = json.loads(res.text)

        # ������ ����� �� ������ ������ �����, ������ ������ "wait", ��������� ������ ����� 5 ������
        if "status" in ans and ans["status"] == "wait":
            time.sleep(5)
        else:
            found = json.loads(res.text)["rows"]
            inn = found[0]["i"]
            break

    # ���������� ��� ������ ��������� �����������
    return inn

# ��������� ���� � ���������� ������ � ���
def get_banks_info(bank_registry, filename):
    banks = []

    if not os.path.isfile(banks_info_file):
        print("%s: �������� ��� ������ �� �����..." % sys.argv[0])
        with open(banks_info_file, "w") as bi:
            for i in tqdm(range(len(bank_registry))):
                # �������� ���
                inn = get_inn(bank_registry[i]["RegNum"])
                bi.write(("%s\t%s\n" % (bank_registry[i]["ShortName"], inn)))
                # ��������, ����� ���������� �������� �� ������ (���� ������������ ������� ����� ��������,
                # �� ����� �������� �����)
                time.sleep(1)

    # ������ ���� � ������ �����
    with open(filename, "r") as f:
        lines = f.readlines()

    # ���� � ����� ��������� ����������
    for l in lines:
        fields = l.split("\t")
        banks.append({"name": fields[0], "inn": fields[1].rstrip()})

    # ������� �� ������ �����, � ������� ��� ���
    banks = list(filter(lambda x: x["inn"] != "", banks))
    print("%s: ���������� ������ � ������� � ��������� ���: %d." % (sys.argv[0], len(banks)))

    return banks

# ��������� ��������� �� ��������� ������ ��� ���������� ���������� ����� (�������� ���)
def get_contracts(start_date, stop_date, inn):
    contracts = []

    # ������������ ������
    url = 'http://openapi.clearspending.ru/restapi/v3/contracts/select/?'
    # ������
    url += "&daterange=%s-%s" % (start_date, stop_date)
    # ��� ���������� ����� (�����)
    url += "&supplierinn=%s" % inn
    # ����������� �����
    url += "&fz=44"

    res = requests.get(url)
    num_pages = 0
    try:
        ans = json.loads(res.text)
        if "contracts" in ans:
            # ���������� ����������
            num_contracts = ans["contracts"]["total"]
            # ���������� ������� � ������
            num_pages = int(num_contracts/50) + (num_contracts % 50 != 0)
    except ValueError:
        pass

    # ��������� ��������� �� ���� ������� � ������
    for page in range(1, num_pages+1):
        target = url + ("&page=%s" % page)
        res = requests.get(target)
        contracts += json.loads(res.text)["contracts"]["data"]

    return contracts

if (len(sys.argv) != 3):
    print("Usage: %s <������ ������� ��.��.����> <����� ������� ��.��.����>" % sys.argv[0])
    sys.exit(1)


# ��������� ��������� ��� ���� ������ �� ��������� ������
def get_all_contracts(banks_info, start_date, stop_date):
    all_contracts = []

    # ��� ����� � ����������� �� ���������� �� ��������� ������
    contracts_info_file = "contracts_info_%s_%s.json" % (start_date, stop_date)

    # ���������, �� �������� �� � ��� ��� ������ ����������
    if not os.path.isfile(contracts_info_file):

        if not os.path.isfile(contracts_info_file):
            print("%s: ��������� ��������� ��� ������� ����� �� ������..." % sys.argv[0])
            # ��������� ��������� ��� ������� ���
            for i in tqdm(range(len(banks_info))):
                bank_contracts = get_contracts(start_date=sys.argv[1], stop_date=sys.argv[2], inn=banks_info[i]["inn"])
                all_contracts.append({"name": banks_info[i]["name"], "inn": banks_info[i]["inn"], "contracts": bank_contracts})

            with open(contracts_info_file, "w") as f:
                json.dump(all_contracts, f)

    with open(contracts_info_file) as f:
        data = json.loads(f.readline())

    return data


# ��������� ������ ������
bank_registry = get_bank_registry(bank_registry_file)
# ��������� ��� ������
banks_info = get_banks_info(bank_registry, banks_info_file)
# ��������� ������ ����������
all_contracts = get_all_contracts(banks_info, sys.argv[1], sys.argv[2])

# ������� ������ ����� ���������� �� ������� �����
banks = []
print("%s: �������������� ������ ����������..." % sys.argv[0])
for i in range(len(all_contracts)):
    pricesum = 0
    for c in all_contracts[i]["contracts"]:
        pricesum += c["price"]
    banks.append({"name": all_contracts[i]["name"], "sum": pricesum, "num": len(all_contracts[i]["contracts"])})

# ������� �� ������ �����, � �������� �� ���� ��������� ���������
banks = list(filter(lambda x: x["sum"] != 0, banks))
# ��������� ����� �� ����� ����������� ����������
banks = sorted(banks, key=lambda x: x["sum"], reverse=True)

# ��� ����� ��������� ������ ���������� ������� �����
max_name_len = len(max(banks, key=lambda x: len(x["name"]))["name"])
max_sum_len = len("%.2f" % max(banks, key=lambda x: len("%.2f" % x["sum"]))["sum"])
max_num_len = len("%d" % (max(banks, key=lambda x: len("%d" % x["num"])))["num"])
# ������� ������ ������
for i in range(len(banks)):
    # ������� ���������� � ��� �������: �������� ����� � ����� ����������� ����������
    # ���������� ������� format ��� ������������
    print(("{:<%d} {:>%d} {:>%d}" % (max_name_len, max_num_len, max_sum_len)).format(banks[i]["name"], "%d" % banks[i]["num"], "%.2f" % banks[i]["sum"]))

#������������ ���-10 ������
import matplotlib.pyplot as plt

#����� ��������� ������� ����
plt.rcdefaults()
fig, ax = plt.subplots()

top_num = 10
names = list(map(lambda x: x['name'], banks[:top_num]))#��������� ������ ������ � ����� ������ 10
y_pos = range(top_num)
sums = list(map(lambda x: x['sum'], banks[:top_num]))

ax.barh(y_pos, sums)#���������� �������������� ���������
ax.set_yticks(y_pos)
ax.set_yticklabels(names)#����� �����
ax.invert_yaxis() # labels �������� ������ ����
ax.set_xlabel('����� ����������')#��� ������
ax.set_title('��� ������ �� ����� ����������')#���������
plt.show()#����� ����������� �� �����

