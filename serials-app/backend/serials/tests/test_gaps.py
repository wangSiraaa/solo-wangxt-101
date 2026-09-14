"""缺藏判断：缺号 != 缺藏，合期覆盖两个 slot，停刊后不再应到，逐项可核实。"""
import pytest
from rest_framework.test import APIClient

from serials import rules, services
from serials.models import Frequency, Issue, IssueKind, TitleStatus

from .conftest import make_title

pytestmark = pytest.mark.django_db


def reg(title, **kw):
    return Issue.objects.create(title=title, **kw)


def test_combined_issue_covers_both_slots(monthly_title, locations):
    """两期合刊：第7、8期两个 slot 都由同一物理合刊满足，8期不算缺号。"""
    combined = reg(
        monthly_title, kind=IssueKind.COMBINED,
        pub_year=2024, pub_month=7, volume=1, number=7, number_end=8,
    )
    services.check_in(issue_id=combined.id, barcode="C-78",
                      location_id=locations["xk"].id)
    analysis = rules.analyze_title(monthly_title, upto=(2024, 8))
    by_number = {r.slot.number: r for r in analysis.rows}
    assert by_number[7].state == rules.HELD
    assert by_number[8].state == rules.HELD
    assert by_number[7].issue.id == by_number[8].issue.id == combined.id
    # 其余未登记的 slot 是缺号而不是缺藏
    assert by_number[1].state == rules.NOT_PUBLISHED


def test_missing_vs_not_published(monthly_title, locations):
    """已出版无实体=缺藏；无出版登记=缺号。两者必须区分。"""
    published = reg(monthly_title, kind=IssueKind.REGULAR,
                    pub_year=2024, pub_month=1, volume=1, number=1)
    assert published.items.count() == 0
    analysis = rules.analyze_title(monthly_title, upto=(2024, 2))
    by_number = {r.slot.number: r for r in analysis.rows}
    assert by_number[1].state == rules.MISSING          # 缺藏
    assert by_number[2].state == rules.NOT_PUBLISHED    # 缺号
    assert analysis.stats["missing"] == 1
    assert analysis.stats["not_published"] == 1


def test_held_after_checkin(monthly_title, locations):
    issue = reg(monthly_title, kind=IssueKind.REGULAR,
                pub_year=2024, pub_month=1, volume=1, number=1)
    services.check_in(issue_id=issue.id, barcode="B-1", location_id=locations["xk"].id)
    analysis = rules.analyze_title(monthly_title, upto=(2024, 1))
    assert analysis.rows[0].state == rules.HELD
    assert analysis.rows[0].items[0].barcode == "B-1"


def test_ceased_months_produce_no_gaps(locations):
    title = make_title(
        name="地质季刊", frequency=Frequency.QUARTERLY,
        status=TitleStatus.CEASED, ceased_year=2024, ceased_month=4,
    )
    analysis = rules.analyze_title(title, upto=(2026, 12))
    months = [(r.slot.year, r.slot.month) for r in analysis.rows]
    assert months == [(2024, 1), (2024, 4)]  # 停刊后的月份根本不应到


def test_supplement_not_in_slots(monthly_title, locations):
    reg(monthly_title, kind=IssueKind.SUPPLEMENT,
        pub_year=2024, pub_month=5, supplement_no=1)
    analysis = rules.analyze_title(monthly_title, upto=(2024, 6))
    assert len(analysis.supplements) == 1
    assert all(r.issue is None or r.issue.kind != IssueKind.SUPPLEMENT for r in analysis.rows)


def test_gaps_endpoint_itemized(monthly_title, locations):
    """缺藏清单逐项给出核实提示；合期覆盖的期号不出现在清单里。"""
    reg(monthly_title, kind=IssueKind.REGULAR,
        pub_year=2024, pub_month=1, volume=1, number=1)          # 缺藏
    combined = reg(monthly_title, kind=IssueKind.COMBINED,
                   pub_year=2024, pub_month=7, volume=1, number=7, number_end=8)
    services.check_in(issue_id=combined.id, barcode="C-78",
                      location_id=locations["xk"].id)
    client = APIClient()
    data = client.get(f"/api/titles/{monthly_title.id}/gaps/").json()
    gaps = data["gaps"]
    by_ym = {(g["year"], g["month"]): g for g in gaps}
    assert by_ym[(2024, 1)]["state"] == "MISSING"
    assert "缺藏" in by_ym[(2024, 1)]["state_display"]
    assert "逐项核对" in by_ym[(2024, 1)]["verification"]
    assert (2024, 7) not in by_ym and (2024, 8) not in by_ym   # 合期已覆盖
    assert by_ym[(2024, 2)]["state"] == "NOT_PUBLISHED"
    assert "缺号不等于缺藏" in by_ym[(2024, 2)]["verification"]


def test_timeline_endpoint_shape(monthly_title, locations):
    issue = reg(monthly_title, kind=IssueKind.REGULAR,
                pub_year=2024, pub_month=1, volume=1, number=1)
    services.check_in(issue_id=issue.id, barcode="B-1", location_id=locations["xk"].id)
    client = APIClient()
    data = client.get(f"/api/titles/{monthly_title.id}/timeline/").json()
    assert data["stats"]["expected"] >= 1
    slot1 = next(s for s in data["slots"] if s["number"] == 1)
    assert slot1["state"] == "HELD"
    assert slot1["items"][0]["barcode"] == "B-1"
    assert slot1["items"][0]["effective_location"]["code"] == "XK-1F"


def test_lineage_endpoint(db):
    pred = make_title(name="城市水利通讯", status=TitleStatus.CEASED,
                      ceased_year=2023, ceased_month=12)
    curr = make_title(name="城市水利月刊", predecessor=pred)
    client = APIClient()
    data = client.get(f"/api/titles/{curr.id}/lineage/").json()
    assert data["ancestors"][0]["name"] == "城市水利通讯"
    assert data["current"]["name"] == "城市水利月刊"
