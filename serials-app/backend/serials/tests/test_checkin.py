"""入藏：并发同编号实体不合并、条码唯一、复本号递增、日志完整。"""
import threading

import pytest
from rest_framework.test import APIClient

from serials import services
from serials.models import Item, OperationLog, OperationType

from .conftest import make_issue

pytestmark = pytest.mark.django_db


def test_checkin_assigns_incrementing_copy_numbers(monthly_title, locations):
    issue = make_issue(monthly_title)
    a = services.check_in(issue_id=issue.id, barcode="B-1", location_id=locations["xk"].id)
    b = services.check_in(issue_id=issue.id, barcode="B-2", location_id=locations["xk"].id)
    assert (a.copy_no, b.copy_no) == (1, 2)
    assert a.pk != b.pk  # 同编号（同单元）两册是不同实体


def test_duplicate_barcode_rejected(monthly_title, locations):
    issue = make_issue(monthly_title)
    services.check_in(issue_id=issue.id, barcode="B-1", location_id=locations["xk"].id)
    with pytest.raises(services.DuplicateBarcode):
        services.check_in(issue_id=issue.id, barcode="B-1", location_id=locations["xk"].id)
    assert Item.objects.filter(issue=issue).count() == 1


def test_checkin_api_creates_log(monthly_title, locations):
    issue = make_issue(monthly_title)
    client = APIClient()
    resp = client.post(
        "/api/items/check_in/",
        {"issue_id": issue.id, "barcode": "B-9", "location_id": locations["xk"].id, "actor": "tester"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    log = OperationLog.objects.get(type=OperationType.CHECK_IN)
    assert log.actor == "tester"
    assert log.item.barcode == "B-9"
    assert log.to_location.code == "XK-1F"


def test_checkin_api_rejects_duplicate_barcode(monthly_title, locations):
    issue = make_issue(monthly_title)
    client = APIClient()
    payload = {"issue_id": issue.id, "barcode": "B-1", "location_id": locations["xk"].id}
    assert client.post("/api/items/check_in/", payload, format="json").status_code == 201
    resp = client.post("/api/items/check_in/", payload, format="json")
    assert resp.status_code == 400
    assert "禁止合并" in resp.json()["detail"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkin_same_issue_not_merged(monthly_title, locations):
    """8 个线程并发入藏同一单元：应得到 8 条实体，复本号 1..8 各一次。"""
    issue = make_issue(monthly_title)
    errors = []

    def worker(i):
        try:
            services.check_in(
                issue_id=issue.id,
                barcode=f"CC-{i}",
                location_id=locations["xk"].id,
                actor=f"t{i}",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发入藏出错: {errors!r}"
    items = Item.objects.filter(issue=issue)
    assert items.count() == 8                      # 不合并
    assert sorted(items.values_list("copy_no", flat=True)) == list(range(1, 9))
    assert len({it.barcode for it in items}) == 8  # 条码各自唯一
