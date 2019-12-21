# -*- coding: cp1251 -*-
import sys
import urllib.request
import json

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
    ans = json.loads(res.text)
    if "contracts" in ans:
        # ���������� ����������
        num_contracts = ans["contracts"]["total"]
        # ���������� ������� � ������
        num_pages = num_contracts / 50 + (num_contracts % 50 != 0)

        for page in range(1, num_pages+1):
            target = url + ("&page=%s" % page)
            res = requests.get(target)
            contracts += json.loads(res.text)["contracts"]["data"]

    return contracts


if len(sys.argv) != 4:
    print ("Usage: %s start_date stop_date supplier_inn" % sys.argv[0])
    sys.exit(1)

get_contracts(sys.argv[1], sys.argv[2], sys.argv[3])
