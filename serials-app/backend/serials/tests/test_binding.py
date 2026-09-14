"""合订 / 拆订 / 移库：子期可检索所在册，拆订逐册恢复位置。"""
import pytest
from rest_framework.test import APIClient

from serials import services
from serials.models import (
    BoundVolumeStatus,
    ItemStatus,
    OperationLog,
    OperationType,
)

from .conftest import make_issue, make_title

pytestmark = pytest.mark.django_db


def checkin(issue, barcode, loc):
    return services.check_in(issue_id=issue.id, barcode=barcode, location_id=loc.id)


def test_bind_marks_items_and_child_issue_searchable(monthly_title, locations):
    i1, i2, i3 = (make_issue(monthly_title, number=n) for n in (1, 2, 3))
    a = checkin(i1, "B-1", locations["xk"])
    b = checkin(i2, "B-2", locations["xk"])
    c = checkin(i3, "B-3", locations["xk"])

    bv = services.bind_items(
        item_ids=[a.id, b.id, c.id], barcode="BV-1",
        label="2024年1-3期合订本", location_id=locations["gk"].id,
    )
    for item in (a, b, c):
        item.refresh_from_db()
        assert item.status == ItemStatus.BOUND
        assert item.bound_volume_id == bv.id
        assert item.effective_location.code == "GK-2F"  # 实际位置随合订本

    # 子期仍能检索到所在册：期详情里每册都指向合订本及其位置
    client = APIClient()
    data = client.get(f"/api/issues/{i2.id}/").json()
    assert data["items"][0]["bound_volume"]["barcode"] == "BV-1"
    assert data["items"][0]["effective_location"]["code"] == "GK-2F"

    # 时间轴上同样可见合订本位置
    tl = client.get(f"/api/titles/{monthly_title.id}/timeline/").json()
    slot2 = next(s for s in tl["slots"] if s["number"] == 2 and s["year"] == 2024)
    assert slot2["items"][0]["bound_volume"]["barcode"] == "BV-1"


def test_unbind_restores_each_items_own_location(monthly_title, locations):
    """拆订必须逐册恢复各自装订前位置——不是只覆盖一个条码。"""
    i1, i2 = make_issue(monthly_title, number=1), make_issue(monthly_title, number=2)
    a = checkin(i1, "B-1", locations["xk"])
    b = checkin(i2, "B-2", locations["mj"])  # 两册装订前位置不同

    bv = services.bind_items(
        item_ids=[a.id, b.id], barcode="BV-1", label="合订本",
        location_id=locations["gk"].id,
    )
    services.unbind(bound_volume_id=bv.id)

    a.refresh_from_db()
    b.refresh_from_db()
    bv.refresh_from_db()
    assert a.location.code == "XK-1F"   # 各回各位
    assert b.location.code == "MJ-B1"
    assert a.status == b.status == ItemStatus.ON_SHELF
    assert a.bound_volume_id is None and b.bound_volume_id is None
    assert bv.status == BoundVolumeStatus.UNBOUND
    assert bv.unbound_at is not None

    log = OperationLog.objects.get(type=OperationType.UNBIND)
    restored = {r["barcode"]: r["restored_location"] for r in log.payload["restored"]}
    assert restored == {"B-1": "XK-1F", "B-2": "MJ-B1"}


def test_bind_rejects_already_bound_item(monthly_title, locations):
    i1, i2 = make_issue(monthly_title, number=1), make_issue(monthly_title, number=2)
    a = checkin(i1, "B-1", locations["xk"])
    b = checkin(i2, "B-2", locations["xk"])
    services.bind_items(item_ids=[a.id], barcode="BV-1", label="v1", location_id=locations["gk"].id)
    with pytest.raises(services.InvalidState):
        services.bind_items(item_ids=[a.id, b.id], barcode="BV-2", label="v2",
                            location_id=locations["gk"].id)


def test_bind_requires_single_title(monthly_title, locations):
    other = make_title(name="另一种刊")
    a = checkin(make_issue(monthly_title, number=1), "B-1", locations["xk"])
    b = checkin(make_issue(other, number=1), "B-2", locations["xk"])
    with pytest.raises(services.DomainError):
        services.bind_items(item_ids=[a.id, b.id], barcode="BV-1", label="v",
                            location_id=locations["gk"].id)


def test_unbind_twice_rejected(monthly_title, locations):
    a = checkin(make_issue(monthly_title, number=1), "B-1", locations["xk"])
    bv = services.bind_items(item_ids=[a.id], barcode="BV-1", label="v",
                             location_id=locations["gk"].id)
    services.unbind(bound_volume_id=bv.id)
    with pytest.raises(services.InvalidState):
        services.unbind(bound_volume_id=bv.id)


def test_move_item_logged_and_bound_item_forbidden(monthly_title, locations):
    a = checkin(make_issue(monthly_title, number=1), "B-1", locations["xk"])
    services.move_item(item_id=a.id, to_location_id=locations["gk"].id)
    a.refresh_from_db()
    assert a.location.code == "GK-2F"
    log = OperationLog.objects.get(type=OperationType.MOVE_ITEM)
    assert log.from_location.code == "XK-1F" and log.to_location.code == "GK-2F"

    bv = services.bind_items(item_ids=[a.id], barcode="BV-1", label="v",
                             location_id=locations["gk"].id)
    with pytest.raises(services.InvalidState):
        services.move_item(item_id=a.id, to_location_id=locations["mj"].id)

    # 合订本整体移库，子册实际位置随之改变
    services.move_bound_volume(bound_volume_id=bv.id, to_location_id=locations["mj"].id)
    a.refresh_from_db()
    assert a.effective_location.code == "MJ-B1"
    assert OperationLog.objects.filter(type=OperationType.MOVE_VOLUME).count() == 1


def test_move_history_api(monthly_title, locations):
    a = checkin(make_issue(monthly_title, number=1), "B-1", locations["xk"])
    services.move_item(item_id=a.id, to_location_id=locations["gk"].id)
    client = APIClient()
    history = client.get(f"/api/items/{a.id}/history/").json()
    types = [h["type"] for h in history]
    assert OperationType.MOVE_ITEM in types and OperationType.CHECK_IN in types
