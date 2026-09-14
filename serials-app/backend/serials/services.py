"""馆藏操作服务层：入藏 / 合订 / 拆订 / 移库 / 改号 / 复刊 / 拆分 / 注销。

并发约定：
  * check_in 事务首语句即 UPDATE Issue.copies_checked_in（PostgreSQL 行锁、
    SQLite 写锁），并发入藏同一单元只产生不同复本号的多条实体，绝不合并。
  * 条码全局唯一，重复条码直接拒绝。
改号约定：
  * renumber_issue 只新增 NumberAssignment 版本并关闭旧版本，Issue 身份与
    Item 实体记录不变——实体不因改号重复生成；合订册内改号不动册序
    （BoundVolumeItem.position），索引候选由当前编号派生自动更新。
"""
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    BoundVolume,
    BoundVolumeItem,
    BoundVolumeStatus,
    Issue,
    IssueKind,
    Item,
    ItemStatus,
    Location,
    NumberAssignment,
    OperationLog,
    OperationType,
    Title,
    TitleStatus,
)

MAX_RETRIES = 5


class DomainError(Exception):
    """业务规则错误，视图层转换为 400。"""


class DuplicateBarcode(DomainError):
    pass


class InvalidState(DomainError):
    pass


def _log(type_, *, actor="system", title=None, issue=None, item=None,
         bound_volume=None, from_location=None, to_location=None, payload=None):
    return OperationLog.objects.create(
        type=type_,
        actor=actor or "system",
        title=title,
        issue=issue,
        item=item,
        bound_volume=bound_volume,
        from_location=from_location,
        to_location=to_location,
        payload=payload or {},
    )


# ---------------------------------------------------------------- 入藏

def check_in(*, issue_id, barcode, location_id, actor="system") -> Item:
    """入藏一册。同编号（同单元）实体各自成行，并发安全。"""
    barcode = (barcode or "").strip()
    if not barcode:
        raise DomainError("条码不能为空")
    if Item.objects.filter(barcode=barcode).exists():
        raise DuplicateBarcode(f"条码 {barcode} 已存在：同编号实体须使用各自条码，禁止合并")
    last_exc = None
    for _ in range(MAX_RETRIES):
        try:
            with transaction.atomic():
                # 首语句即 UPDATE：PostgreSQL 取行锁、SQLite 立即取写锁，
                # 并发入藏同一单元在此串行化，各自拿到不同复本号。
                Issue.objects.filter(pk=issue_id).update(
                    copies_checked_in=F("copies_checked_in") + 1
                )
                issue = Issue.objects.get(pk=issue_id)
                copy_no = issue.copies_checked_in
                location = Location.objects.get(pk=location_id)
                item = Item.objects.create(
                    issue=issue, copy_no=copy_no, barcode=barcode, location=location
                )
                _log(
                    OperationType.CHECK_IN,
                    actor=actor,
                    title=issue.title,
                    issue=issue,
                    item=item,
                    to_location=location,
                    payload={"barcode": barcode, "copy_no": copy_no},
                )
                return item
        except IntegrityError as exc:
            last_exc = exc
            if Item.objects.filter(barcode=barcode).exists():
                raise DuplicateBarcode(f"条码 {barcode} 已存在：同编号实体须使用各自条码，禁止合并")
            continue  # (issue, copy_no) 并发冲突，重试取下一个复本号
        except OperationalError as exc:
            # SQLite 快照升级冲突（PostgreSQL 由行锁保证，不会走到这里）
            last_exc = exc
            if "locked" not in str(exc).lower():
                raise
            continue
    raise DomainError("入藏失败：并发冲突过多，请重试") from last_exc


# ---------------------------------------------------------------- 期登记与改号

def _validate_numbering(kind, volume, number, number_end):
    if kind == IssueKind.SUPPLEMENT:
        return
    if volume is None or number is None:
        raise DomainError("正期/合期必须登记卷期编号")
    if kind == IssueKind.COMBINED:
        if number_end is None or number_end <= number:
            raise DomainError("合期必须给出大于起号的止期号")
    elif number_end is not None:
        raise DomainError("非合期不应填写止期号")


def register_issue(*, actor="system", volume=None, number=None, number_end=None, **fields) -> Issue:
    """登记出版单元：身份（发行年月）与显示编号（首版映射）同时建立。"""
    kind = fields.get("kind", IssueKind.REGULAR)
    _validate_numbering(kind, volume, number, number_end)
    issue = Issue(**fields)
    issue.full_clean()
    with transaction.atomic():
        issue.save()
        if kind != IssueKind.SUPPLEMENT:
            assignment = NumberAssignment(
                issue=issue, volume=volume, number=number, number_end=number_end,
                valid_from=timezone.now(), reason="初始登记",
            )
            assignment.full_clean()
            assignment.save()
        _log(
            OperationType.ISSUE_REGISTER,
            actor=actor,
            title=issue.title,
            issue=issue,
            payload={"label": issue.label, "kind": issue.kind},
        )
    return issue


def renumber_issue(*, issue_id, volume, number, number_end=None, reason="", actor="system"):
    """改号：关闭当前编号版本，新增映射版本。

    返回 (issue, collisions)：collisions 为改号后形成的重名单元列表。
    Issue 身份与 Item 实体记录不变；合订册内改号不影响册序。
    """
    with transaction.atomic():
        issue = Issue.objects.select_for_update().select_related("title").get(pk=issue_id)
        if issue.kind == IssueKind.SUPPLEMENT:
            raise DomainError("增刊不参与卷期改号")
        _validate_numbering(issue.kind, volume, number, number_end)
        current = issue.numberings.filter(valid_to__isnull=True).select_for_update().get()
        if (current.volume, current.number, current.number_end) == (volume, number, number_end):
            raise DomainError("新编号与当前编号相同")
        now = timezone.now()
        old_snapshot = {
            "volume": current.volume, "number": current.number,
            "number_end": current.number_end, "valid_from": current.valid_from.isoformat(),
        }
        current.valid_to = now
        current.save(update_fields=["valid_to"])
        assignment = NumberAssignment(
            issue=issue, volume=volume, number=number, number_end=number_end,
            valid_from=now, reason=reason or "出版社更正",
        )
        assignment.full_clean()
        assignment.save()
        # 重名检测：同刊其他单元当前编号是否与之相同
        collisions = []
        for other in Issue.objects.filter(title=issue.title).exclude(pk=issue.pk):
            cur = other.current_numbering
            if cur and cur.volume == volume and cur.number == number:
                collisions.append({"issue_id": other.id, "label": other.label})
        # 合订册内改号：册序不动，仅留痕（索引候选由当前编号派生）
        bound_in = list(
            issue.items.filter(status=ItemStatus.BOUND)
            .values_list("bound_volume__barcode", flat=True)
            .distinct()
        )
        _log(
            OperationType.RENUMBER,
            actor=actor,
            title=issue.title,
            issue=issue,
            payload={
                "old": old_snapshot,
                "new": {"volume": volume, "number": number, "number_end": number_end},
                "reason": reason or "出版社更正",
                "collisions": collisions,
                "in_bound_volumes": bound_in,
            },
        )
    return issue, collisions


def resume_title(*, title_id, note="", actor="system") -> Title:
    """停刊更正：实为延迟出版，恢复在版，应到 slot 自动重算。"""
    with transaction.atomic():
        title = Title.objects.select_for_update().get(pk=title_id)
        if title.status != TitleStatus.CEASED:
            raise DomainError("该刊未处于停刊状态")
        prev = {"year": title.ceased_year, "month": title.ceased_month}
        title.status = TitleStatus.ACTIVE
        title.ceased_year = None
        title.ceased_month = None
        title.save(update_fields=["status", "ceased_year", "ceased_month"])
        _log(
            OperationType.TITLE_RESUME,
            actor=actor,
            title=title,
            payload={"previous_ceased": prev, "note": note or "出版社确认系延迟出版"},
        )
    return title


# ---------------------------------------------------------------- 实体注销

def withdraw_item(*, item_id, reason="", actor="system") -> Item:
    """注销一册（如馆员决定不再保留合刊实体）。注销后不计入可借实体。"""
    with transaction.atomic():
        item = (
            Item.objects.select_for_update()
            .select_related("issue__title", "location")
            .get(pk=item_id)
        )
        if item.status == ItemStatus.WITHDRAWN:
            raise InvalidState(f"册 {item.barcode} 已是注销状态")
        if item.status == ItemStatus.BOUND:
            raise InvalidState(f"册 {item.barcode} 已装订，须先拆订才能注销")
        previous = item.status
        item.status = ItemStatus.WITHDRAWN
        item.save(update_fields=["status"])
        _log(
            OperationType.WITHDRAW_ITEM,
            actor=actor,
            title=item.issue.title,
            issue=item.issue,
            item=item,
            from_location=item.location,
            payload={
                "barcode": item.barcode,
                "previous_status": previous,
                "reason": reason or "馆员决定注销",
            },
        )
        return item


# ---------------------------------------------------------------- 合订 / 拆订 / 拆分

def bind_items(*, item_ids, barcode, label, location_id, actor="system") -> BoundVolume:
    """把若干在架册合订为一册合订本。子期与册保留，可检索到所在合订本。"""
    barcode = (barcode or "").strip()
    if not barcode:
        raise DomainError("合订本条码不能为空")
    if BoundVolume.objects.filter(barcode=barcode).exists():
        raise DuplicateBarcode(f"合订本条码 {barcode} 已存在")
    item_ids = list(dict.fromkeys(item_ids or []))
    if not item_ids:
        raise DomainError("至少选择一册进行合订")
    with transaction.atomic():
        items = list(
            Item.objects.select_for_update()
            .select_related("issue__title", "location")
            .filter(pk__in=item_ids)
            .order_by("issue__pub_year", "issue__pub_month", "issue_id", "copy_no")
        )
        if len(items) != len(item_ids):
            raise DomainError("存在无效的册 ID")
        bad = [it.barcode for it in items if it.status != ItemStatus.ON_SHELF]
        if bad:
            raise InvalidState(f"以下册不在在架状态，不能合订：{', '.join(bad)}")
        title_ids = {it.issue.title_id for it in items}
        if len(title_ids) != 1:
            raise DomainError("只能合订同一刊名的册")
        title = items[0].issue.title
        location = Location.objects.get(pk=location_id)
        bv = BoundVolume.objects.create(
            title=title,
            barcode=barcode,
            label=label or f"{title.name} 合订本",
            location=location,
        )
        for position, item in enumerate(items, start=1):
            BoundVolumeItem.objects.create(
                bound_volume=bv,
                item=item,
                position=position,
                pre_location=item.location,   # 冻结装订前状态，供拆订逐册恢复
                pre_status=item.status,
            )
            item.status = ItemStatus.BOUND
            item.bound_volume = bv
            item.save(update_fields=["status", "bound_volume"])
        _log(
            OperationType.BIND,
            actor=actor,
            title=title,
            bound_volume=bv,
            to_location=location,
            payload={
                "barcode": barcode,
                "label": bv.label,
                "items": [
                    {"item_id": it.id, "barcode": it.barcode, "issue": it.issue.label}
                    for it in items
                ],
            },
        )
        return bv


def unbind(*, bound_volume_id, actor="system") -> BoundVolume:
    """拆订：逐册恢复装订前的位置与状态（不是只覆盖一个条码）。"""
    with transaction.atomic():
        bv = (
            BoundVolume.objects.select_for_update()
            .select_related("title", "location")
            .get(pk=bound_volume_id)
        )
        if bv.status != BoundVolumeStatus.ACTIVE:
            raise InvalidState(f"合订本 {bv.barcode} 已是拆订状态")
        now = timezone.now()
        restored = []
        records = list(bv.bound_items.select_related("item__issue", "pre_location"))
        for record in records:
            item = record.item
            item.status = record.pre_status
            item.location = record.pre_location
            item.bound_volume = None
            item.save(update_fields=["status", "location", "bound_volume"])
            record.unbound_at = now
            record.save(update_fields=["unbound_at"])
            restored.append(
                {
                    "item_id": item.id,
                    "barcode": item.barcode,
                    "restored_location": record.pre_location.code,
                    "restored_status": record.pre_status,
                }
            )
        bv.status = BoundVolumeStatus.UNBOUND
        bv.unbound_at = now
        bv.save(update_fields=["status", "unbound_at"])
        _log(
            OperationType.UNBIND,
            actor=actor,
            title=bv.title,
            bound_volume=bv,
            from_location=bv.location,
            payload={"barcode": bv.barcode, "restored": restored},
        )
        return bv


def split_bound_volume(*, bound_volume_id, item_ids, new_barcode, new_label="",
                       location_id=None, actor="system") -> BoundVolume:
    """合订册拆分：把部分成员移入新合订本，两侧均保留原有相对册序。"""
    new_barcode = (new_barcode or "").strip()
    if not new_barcode:
        raise DomainError("新合订本条码不能为空")
    if BoundVolume.objects.filter(barcode=new_barcode).exists():
        raise DuplicateBarcode(f"合订本条码 {new_barcode} 已存在")
    item_ids = list(dict.fromkeys(item_ids or []))
    if not item_ids:
        raise DomainError("至少选择一册进行拆分")
    with transaction.atomic():
        bv = BoundVolume.objects.select_for_update().select_related("title", "location").get(
            pk=bound_volume_id
        )
        if bv.status != BoundVolumeStatus.ACTIVE:
            raise InvalidState(f"合订本 {bv.barcode} 已拆订，不能拆分")
        current_records = list(
            bv.bound_items.filter(unbound_at__isnull=True)
            .select_related("item__issue")
            .order_by("position")
        )
        moving = [r for r in current_records if r.item_id in item_ids]
        if len(moving) != len(item_ids):
            raise DomainError("拆分对象必须全部属于该合订本且未拆出")
        if len(moving) == len(current_records):
            raise DomainError("不能拆分全部成员（如需整体处理请使用拆订）")
        location = Location.objects.get(pk=location_id) if location_id else bv.location
        new_bv = BoundVolume.objects.create(
            title=bv.title,
            barcode=new_barcode,
            label=new_label or f"{bv.label}（拆分）",
            location=location,
        )
        # 移出成员：按原相对顺序重新编号册序
        moved_barcodes = []
        for position, record in enumerate(moving, start=1):
            record.bound_volume = new_bv
            record.position = position
            record.save(update_fields=["bound_volume", "position"])
            record.item.bound_volume = new_bv
            record.item.save(update_fields=["bound_volume"])
            moved_barcodes.append(record.item.barcode)
        # 留存成员：保持相对顺序，补齐册序
        remaining = [r for r in current_records if r.item_id not in item_ids]
        for position, record in enumerate(remaining, start=1):
            if record.position != position:
                record.position = position
                record.save(update_fields=["position"])
        _log(
            OperationType.SPLIT_VOLUME,
            actor=actor,
            title=bv.title,
            bound_volume=bv,
            to_location=location,
            payload={
                "from_barcode": bv.barcode,
                "new_barcode": new_bv.barcode,
                "moved": moved_barcodes,
                "note": "两侧成员均保留原有相对装订顺序",
            },
        )
        return new_bv


# ---------------------------------------------------------------- 移库

def move_item(*, item_id, to_location_id, actor="system") -> Item:
    with transaction.atomic():
        item = Item.objects.select_for_update().select_related("issue__title", "location").get(pk=item_id)
        if item.status == ItemStatus.BOUND:
            raise InvalidState(
                f"册 {item.barcode} 已装订于合订本 {item.bound_volume.barcode}，"
                "请对合订本整体移库"
            )
        if item.status == ItemStatus.WITHDRAWN:
            raise InvalidState(f"册 {item.barcode} 已注销，不能移库")
        to_location = Location.objects.get(pk=to_location_id)
        from_location = item.location
        if from_location.pk == to_location.pk:
            raise DomainError("目标位置与当前位置相同")
        item.location = to_location
        item.save(update_fields=["location"])
        _log(
            OperationType.MOVE_ITEM,
            actor=actor,
            title=item.issue.title,
            issue=item.issue,
            item=item,
            from_location=from_location,
            to_location=to_location,
            payload={"barcode": item.barcode},
        )
        return item


def move_bound_volume(*, bound_volume_id, to_location_id, actor="system") -> BoundVolume:
    with transaction.atomic():
        bv = BoundVolume.objects.select_for_update().get(pk=bound_volume_id)
        if bv.status != BoundVolumeStatus.ACTIVE:
            raise InvalidState(f"合订本 {bv.barcode} 已拆订，不能移库")
        to_location = Location.objects.get(pk=to_location_id)
        from_location = bv.location
        if from_location.pk == to_location.pk:
            raise DomainError("目标位置与当前位置相同")
        bv.location = to_location
        bv.save(update_fields=["location"])
        _log(
            OperationType.MOVE_VOLUME,
            actor=actor,
            title=bv.title,
            bound_volume=bv,
            from_location=from_location,
            to_location=to_location,
            payload={"barcode": bv.barcode},
        )
        return bv
