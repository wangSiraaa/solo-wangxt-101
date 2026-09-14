"""编号更正与补寄场景：映射版本、重名、延迟出版、合订册拆分、可解释缺藏。"""
import pytest
from rest_framework.test import APIClient

from serials import rules, services
from serials.models import (
    BoundVolumeStatus,
    Frequency,
    IssueKind,
    Item,
    ItemStatus,
    NumberAssignment,
    OperationLog,
    OperationType,
    TitleStatus,
)

from .conftest import make_issue, make_title

pytestmark = pytest.mark.django_db


def checkin(issue, barcode, loc):
    return services.check_in(issue_id=issue.id, barcode=barcode, location_id=loc.id)


# ---------------------------------------------------------------- 改号

def test_renumber_keeps_identity_and_items(monthly_title, locations):
    """改号：单元身份不变，实体记录不重复生成，旧编号仍可检索。"""
    issue = make_issue(monthly_title, number=9, pub_month=9)
    item = checkin(issue, "B-9", locations["xk"])
    items_before = list(Item.objects.filter(issue=issue).values_list("barcode", flat=True))

    issue, collisions = services.renumber_issue(
        issue_id=issue.id, volume=1, number=10, reason="出版社更正"
    )

    assert collisions == []
    assert Item.objects.filter(issue=issue).count() == 1          # 实体不重复生成
    assert list(Item.objects.filter(issue=issue).values_list("barcode", flat=True)) == items_before
    item.refresh_from_db()
    assert item.issue_id == issue.id                              # 仍挂在同一单元
    # 编号版本：旧版关闭、新版生效
    versions = issue.numberings.order_by("valid_from")
    assert versions.count() == 2
    assert versions[0].number == 9 and versions[0].valid_to is not None
    assert versions[1].number == 10 and versions[1].valid_to is None
    assert issue.current_numbering.number == 10
    # 改号留痕
    log = OperationLog.objects.get(type=OperationType.RENUMBER)
    assert log.payload["old"]["number"] == 9 and log.payload["new"]["number"] == 10


def test_renumber_collision_creates_duplicate_name(monthly_title, locations):
    """改号形成重名：两个单元当前编号相同，检索时各自指向自己的实体。"""
    issue9 = make_issue(monthly_title, number=9, pub_month=9)
    issue10 = make_issue(monthly_title, number=10, pub_month=10)
    checkin(issue9, "B-9", locations["xk"])
    checkin(issue10, "B-10", locations["xk"])

    issue9, collisions = services.renumber_issue(
        issue_id=issue9.id, volume=1, number=10, reason="出版社更正：第9期应为第10期"
    )
    assert [c["issue_id"] for c in collisions] == [issue10.id]    # 重名告警

    client = APIClient()
    # 按当前编号检索 (1,10)：两个单元都命中，各自实体不串
    data = client.get(f"/api/lookup/numbering/?title={monthly_title.id}&volume=1&number=10").json()
    assert len(data["matches"]) == 2
    by_issue = {m["issue"]["id"]: m for m in data["matches"]}
    assert by_issue[issue9.id]["items"][0]["barcode"] == "B-9"
    assert by_issue[issue10.id]["items"][0]["barcode"] == "B-10"
    # 旧编号 (1,9) 仍能检索，且指向原单元（历史目录链接不指向错误实体）
    old = client.get(f"/api/lookup/numbering/?title={monthly_title.id}&volume=1&number=9").json()
    assert len(old["matches"]) == 1
    assert old["matches"][0]["issue"]["id"] == issue9.id
    assert old["matches"][0]["assignment"]["is_current"] is False
    # 时间轴上报重名
    tl = client.get(f"/api/titles/{monthly_title.id}/timeline/").json()
    assert tl["collisions"][0]["number"] == 10
    assert set(tl["collisions"][0]["issue_ids"]) == {issue9.id, issue10.id}


def test_lookup_with_time_point_resolves_historical(monthly_title, locations):
    """按时间点检索：历史目录链接解析到当时持有该编号的正确单元。"""
    issue = make_issue(monthly_title, number=9, pub_month=9)
    checkin(issue, "B-9", locations["xk"])
    old_version = issue.current_numbering
    services.renumber_issue(issue_id=issue.id, volume=1, number=10, reason="更正")
    issue.refresh_from_db()

    client = APIClient()
    at = old_version.valid_from.isoformat().replace("+00:00", "Z")
    data = client.get(
        f"/api/lookup/numbering/?title={monthly_title.id}&volume=1&number=9&at={at}"
    ).json()
    assert len(data["matches"]) == 1
    assert data["matches"][0]["issue"]["id"] == issue.id
    # 当前时间点查旧编号：只有历史版本命中
    now = client.get(f"/api/lookup/numbering/?title={monthly_title.id}&volume=1&number=9").json()
    assert all(not m["assignment"]["is_current"] for m in now["matches"])


def test_renumber_recaculates_coverage(monthly_title, locations):
    """改号后覆盖重算：原 slot 变缺号并给出解释，新 slot 变为在藏。"""
    issue = make_issue(monthly_title, number=9, pub_month=9)
    checkin(issue, "B-9", locations["xk"])
    services.renumber_issue(issue_id=issue.id, volume=1, number=10, reason="更正")

    analysis = rules.analyze_title(monthly_title, upto=(2024, 10))
    by_number = {r.slot.number: r for r in analysis.rows}
    assert by_number[9].state == rules.NOT_PUBLISHED
    assert any("改号为" in e for e in by_number[9].explanation)   # 缺号原因可解释
    assert by_number[10].state == rules.HELD
    assert by_number[10].items[0].barcode == "B-9"


def test_renumber_inside_bound_volume_keeps_order(monthly_title, locations):
    """已合订册内改号：索引候选更新，原装订顺序保留。"""
    issues = [make_issue(monthly_title, number=n) for n in (1, 2, 3)]
    items = [checkin(i, f"B-{n}", locations["xk"]) for n, i in enumerate(issues, 1)]
    bv = services.bind_items(
        item_ids=[it.id for it in items], barcode="BV-1", label="合订本",
        location_id=locations["gk"].id,
    )
    services.renumber_issue(issue_id=issues[1].id, volume=1, number=20, reason="更正")

    client = APIClient()
    data = client.get(f"/api/bound-volumes/{bv.id}/").json()
    candidates = data["index_candidates"]
    # 装订顺序不变
    assert [c["position"] for c in candidates] == [1, 2, 3]
    assert [c["barcode"] for c in candidates] == ["B-1", "B-2", "B-3"]
    # 索引候选已更新为新编号，历史别名保留
    assert candidates[1]["current_number"] == "第1卷 第20期"
    assert candidates[1]["aliases"] == ["第1卷 第2期"]
    # 册序记录未被改动
    positions = [r.position for r in bv.bound_items.order_by("position")]
    assert positions == [1, 2, 3]


def test_renumber_rejects_same_number(monthly_title, locations):
    issue = make_issue(monthly_title, number=9, pub_month=9)
    with pytest.raises(services.DomainError):
        services.renumber_issue(issue_id=issue.id, volume=1, number=9)


# ---------------------------------------------------------------- 停刊更正（延迟出版）

def test_resume_title_recaculates_gaps(locations):
    """停刊后来改为延迟出版：应到重算，缺口可解释。"""
    title = make_title(
        name="地质季刊", frequency=Frequency.QUARTERLY,
        status=TitleStatus.CEASED, ceased_year=2024, ceased_month=4,
    )
    before = rules.analyze_title(title, upto=(2024, 12))
    assert len(before.rows) == 2                                  # 停刊后不应到

    services.resume_title(title_id=title.id, note="出版社确认系延迟出版")
    title.refresh_from_db()
    assert title.status == TitleStatus.ACTIVE and title.ceased_year is None

    after = rules.analyze_title(title, upto=(2024, 12))
    assert len(after.rows) == 4                                   # 应到重算
    assert any("延迟出版" in n for n in after.title_notes)        # 留痕可解释
    log = OperationLog.objects.get(type=OperationType.TITLE_RESUME)
    assert log.payload["previous_ceased"] == {"year": 2024, "month": 4}

    # 复刊后可登记延迟出版的期
    delayed = make_issue(title, number=3, volume=1, pub_year=2024, pub_month=7)
    checkin(delayed, "DZ-Q3", locations["gk"])
    final = rules.analyze_title(title, upto=(2024, 12))
    q3 = next(r for r in final.rows if (r.slot.year, r.slot.month) == (2024, 7))
    assert q3.state == rules.HELD


def test_resume_rejects_active_title(monthly_title):
    with pytest.raises(services.DomainError):
        services.resume_title(title_id=monthly_title.id)


# ---------------------------------------------------------------- 补寄拆合刊

def test_supplementary_singles_coexist_with_combined(monthly_title, locations):
    """补寄单期到达：与原合刊并存（不自动删合刊），冗余待馆员决定。"""
    combined = make_issue(monthly_title, number=7, number_end=8, kind=IssueKind.COMBINED)
    checkin(combined, "C-78", locations["xk"])
    # 补寄：两本单期到达
    s7 = make_issue(monthly_title, number=7, pub_month=7, kind=IssueKind.REGULAR)
    s8 = make_issue(monthly_title, number=8, pub_month=8, kind=IssueKind.REGULAR)
    checkin(s7, "S-7", locations["xk"])
    checkin(s8, "S-8", locations["xk"])

    analysis = rules.analyze_title(monthly_title, upto=(2024, 8))
    by_number = {r.slot.number: r for r in analysis.rows}
    # 合刊未被自动删除：slot 7 有两个覆盖单元
    assert len(by_number[7].units) == 2
    assert by_number[7].redundant
    assert len(analysis.redundancies) == 2                        # 7、8 两 slot 冗余
    # 内容覆盖不变（仍 2 个 slot 在藏），实体数量分别统计
    assert analysis.stats["coverage"]["held"] == 2
    assert analysis.stats["entities"]["total_lendable"] == 3      # 合刊1 + 单期2


def test_librarian_withdraws_combined_after_singles(monthly_title, locations):
    """馆员决定不保留合刊：注销其实体后，slot 仍由单期满足。"""
    combined = make_issue(monthly_title, number=7, number_end=8, kind=IssueKind.COMBINED)
    combined_item = checkin(combined, "C-78", locations["xk"])
    s7 = make_issue(monthly_title, number=7, pub_month=7)
    checkin(s7, "S-7", locations["xk"])

    services.withdraw_item(item_id=combined_item.id, reason="补寄单期已到，注销合刊复本")
    combined_item.refresh_from_db()
    assert combined_item.status == ItemStatus.WITHDRAWN

    analysis = rules.analyze_title(monthly_title, upto=(2024, 8))
    by_number = {r.slot.number: r for r in analysis.rows}
    assert by_number[7].state == rules.HELD                       # 单期仍在藏
    assert by_number[8].state == rules.MISSING                    # 合刊注销后 8 缺藏
    assert analysis.stats["entities"]["withdrawn"] == 1
    assert analysis.stats["entities"]["total_lendable"] == 1
    # 注销留痕
    log = OperationLog.objects.get(type=OperationType.WITHDRAW_ITEM)
    assert log.payload["barcode"] == "C-78"


def test_withdraw_bound_item_rejected(monthly_title, locations):
    issue = make_issue(monthly_title, number=1)
    item = checkin(issue, "B-1", locations["xk"])
    services.bind_items(item_ids=[item.id], barcode="BV-1", label="v",
                        location_id=locations["gk"].id)
    with pytest.raises(services.InvalidState):
        services.withdraw_item(item_id=item.id)


# ---------------------------------------------------------------- 合订册拆分

def test_split_bound_volume_preserves_order(monthly_title, locations):
    """合订册拆分：成员移入新册，两侧相对册序均保留。"""
    issues = [make_issue(monthly_title, number=n) for n in (1, 2, 3, 4)]
    items = [checkin(i, f"B-{n}", locations["xk"]) for n, i in enumerate(issues, 1)]
    bv = services.bind_items(
        item_ids=[it.id for it in items], barcode="BV-1", label="1-4期合订本",
        location_id=locations["gk"].id,
    )
    new_bv = services.split_bound_volume(
        bound_volume_id=bv.id, item_ids=[items[1].id, items[2].id],
        new_barcode="BV-2", new_label="2-3期分册",
    )
    bv.refresh_from_db()
    # 原册：B-1、B-4，册序补齐为 1、2
    old_members = [(r.position, r.item.barcode) for r in bv.bound_items.order_by("position")]
    assert old_members == [(1, "B-1"), (2, "B-4")]
    # 新册：B-2、B-3 保持原相对顺序
    new_members = [(r.position, r.item.barcode) for r in new_bv.bound_items.order_by("position")]
    assert new_members == [(1, "B-2"), (2, "B-3")]
    # 册仍处已装订状态，指向新合订本
    items[1].refresh_from_db()
    assert items[1].status == ItemStatus.BOUND
    assert items[1].bound_volume_id == new_bv.id
    # 拆分留痕
    log = OperationLog.objects.get(type=OperationType.SPLIT_VOLUME)
    assert log.payload["moved"] == ["B-2", "B-3"]


def test_split_rejects_moving_all(monthly_title, locations):
    issue = make_issue(monthly_title, number=1)
    item = checkin(issue, "B-1", locations["xk"])
    bv = services.bind_items(item_ids=[item.id], barcode="BV-1", label="v",
                             location_id=locations["gk"].id)
    with pytest.raises(services.DomainError):
        services.split_bound_volume(bound_volume_id=bv.id, item_ids=[item.id],
                                    new_barcode="BV-2")


def test_split_rejects_foreign_item(monthly_title, locations):
    i1, i2 = make_issue(monthly_title, number=1), make_issue(monthly_title, number=2)
    a, b = checkin(i1, "B-1", locations["xk"]), checkin(i2, "B-2", locations["xk"])
    bv = services.bind_items(item_ids=[a.id], barcode="BV-1", label="v",
                             location_id=locations["gk"].id)
    with pytest.raises(services.DomainError):
        services.split_bound_volume(bound_volume_id=bv.id, item_ids=[b.id],
                                    new_barcode="BV-2")
