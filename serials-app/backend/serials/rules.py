"""卷期枚举规则与缺藏分析（纯逻辑，不写库）。

规则要点：
  * 发行年月与显示编号分离：slot 由发行规则推出；出版单元（Issue）是稳定
    身份，其当前"显示编号"取自 NumberAssignment 当前版本，覆盖关系跟随
    当前版本——改号后覆盖自动重算，旧版本仅用于检索与解释。
  * 合刊：一个物理单元覆盖 number..number_end 多个 slot；覆盖两个单元
    不等于有两本可借实体——内容覆盖与实体数量分别统计。
  * 补寄单期：与原合刊并存，同一 slot 可被多个单元覆盖（冗余待馆员决定，
    系统不自动删除合刊）。
  * 停刊：ceased_year/ceased_month 之后不产生应到 slot；停刊更正（延迟
    出版）后应到自动重算，并在 title_notes 中留痕。
  * 缺号 != 缺藏：NOT_PUBLISHED（无出版登记）与 MISSING（已出版但无可借
    实体）分别判定，每个 slot 给出可逐项核实的解释。
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .models import (
    FREQUENCY_STEP_MONTHS,
    IssueKind,
    ItemStatus,
    NumberAssignment,
    OperationLog,
    OperationType,
    TitleStatus,
)

# slot 状态
HELD = "HELD"                      # 在藏
MISSING = "MISSING"                # 缺藏：已出版登记，但无可借实体
NOT_PUBLISHED = "NOT_PUBLISHED"    # 缺号：无出版登记（未必缺藏）


def month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def index_to_year_month(idx: int) -> tuple[int, int]:
    return idx // 12, idx % 12 + 1


@dataclass(frozen=True)
class Slot:
    """应到期：某刊按规则在某发行年月应有一期。"""

    year: int
    month: int
    volume: int
    number: int


def expected_slots(title, upto: tuple[int, int] | None = None) -> list[Slot]:
    """按枚举规则生成应到 slot 序列（创刊月起，至停刊月或 upto 止）。"""
    if upto is None:
        today = date.today()
        upto = (today.year, today.month)
    start = month_index(title.start_year, title.start_month)
    if title.status == TitleStatus.CEASED:
        end = month_index(title.ceased_year, title.ceased_month)
    else:
        end = month_index(*upto)
    step = FREQUENCY_STEP_MONTHS[title.frequency]
    v0 = month_index(title.volume_start_year, title.volume_start_month)
    slots: list[Slot] = []
    idx = start
    while idx <= end:
        volume_offset = (idx - v0) // title.months_per_volume
        volume = title.volume_start_number + volume_offset
        volume_start_idx = v0 + volume_offset * title.months_per_volume
        number = (idx - volume_start_idx) // step + 1
        year, month = index_to_year_month(idx)
        slots.append(Slot(year=year, month=month, volume=volume, number=number))
        idx += step
    return slots


def issue_covers(issue) -> list[tuple[int, int]]:
    """该单元在**当前编号版本**下覆盖的 (卷, 期号) 列表。

    合期覆盖多个；增刊不覆盖；改号后跟随新版本。
    """
    if issue.kind == IssueKind.SUPPLEMENT:
        return []
    cur = issue.current_numbering
    if cur is None or cur.volume is None or cur.number is None:
        return []
    end = cur.number_end or cur.number
    return [(cur.volume, n) for n in range(cur.number, end + 1)]


def coverage_map(title) -> dict[tuple[int, int], list]:
    """(卷, 期号) -> [出版单元, ...]：同一 slot 可被多单元覆盖。"""
    cov: dict[tuple[int, int], list] = defaultdict(list)
    for issue in title.issues.all():
        for key in issue_covers(issue):
            cov[key].append(issue)
    return cov


def _fmt_assignment(n: NumberAssignment) -> str:
    if n.volume is None:
        return "（无卷期编号）"
    if n.number_end:
        return f"第{n.volume}卷第{n.number}-{n.number_end}期"
    return f"第{n.volume}卷第{n.number}期"


@dataclass
class SlotRow:
    slot: Slot
    state: str
    units: list = field(default_factory=list)          # 覆盖本 slot 的出版单元
    items: list = field(default_factory=list)          # 可借实体（未注销）
    withdrawn_items: list = field(default_factory=list)  # 已注销实体（不计入）
    explanation: list = field(default_factory=list)    # 判定解释，可逐项核实

    @property
    def redundant(self) -> bool:
        return len(self.units) > 1


@dataclass
class Analysis:
    title: object
    rows: list[SlotRow]
    supplements: list
    redundancies: list          # 多单元覆盖的 slot（补寄待决）
    collisions: list            # 当前编号重名（同卷同期号多单元）
    title_notes: list           # 刊级状态留痕（停刊/停刊更正）
    entity_stats: dict          # 实体数量统计（与内容覆盖分列）

    @property
    def stats(self) -> dict:
        return {
            "coverage": {
                "expected": len(self.rows),
                "held": sum(1 for r in self.rows if r.state == HELD),
                "missing": sum(1 for r in self.rows if r.state == MISSING),
                "not_published": sum(1 for r in self.rows if r.state == NOT_PUBLISHED),
            },
            "entities": self.entity_stats,
        }


def _historical_assignments_for(title, volume: int, number: int):
    """曾以 (volume, number) 对应某 slot、但已改号失效的映射版本。"""
    qs = (
        NumberAssignment.objects.filter(issue__title=title, volume=volume, valid_to__isnull=False)
        .filter(number__lte=number)
        .select_related("issue")
    )
    return [n for n in qs if n.number <= number <= (n.number_end or n.number)]


def _numbering_collisions(title) -> list[dict]:
    """当前编号重名：同刊同卷同期号对应多个单元。"""
    by_key: dict[tuple, list] = defaultdict(list)
    for issue in title.issues.all():
        cur = issue.current_numbering
        if cur and cur.volume is not None:
            by_key[(cur.volume, cur.number)].append(issue)
    collisions = []
    for (volume, number), issues in sorted(by_key.items()):
        if len(issues) > 1:
            collisions.append(
                {
                    "volume": volume,
                    "number": number,
                    "issue_ids": [i.id for i in issues],
                    "labels": [i.label for i in issues],
                }
            )
    return collisions


def _title_notes(title) -> list[str]:
    """刊级状态留痕：当前停刊状态 + 停刊更正历史。"""
    notes = []
    if title.status == TitleStatus.CEASED:
        notes.append(f"当前登记为停刊（最后一期 {title.ceased_year}年{title.ceased_month}月）")
    logs = OperationLog.objects.filter(title=title, type=OperationType.TITLE_RESUME).order_by("created_at")
    for log in logs:
        prev = log.payload.get("previous_ceased") or {}
        notes.append(
            f"{log.created_at:%Y-%m-%d} 由停刊（至{prev.get('year')}年{prev.get('month')}月）"
            f"更正为延迟出版，其后月份重新纳入应到（{log.payload.get('note', '')}）"
        )
    return notes


def _entity_stats(title) -> dict:
    counts = {"on_shelf": 0, "bound": 0, "withdrawn": 0}
    for issue in title.issues.all():
        for item in issue.items.all():
            if item.status == ItemStatus.ON_SHELF:
                counts["on_shelf"] += 1
            elif item.status == ItemStatus.BOUND:
                counts["bound"] += 1
            elif item.status == ItemStatus.WITHDRAWN:
                counts["withdrawn"] += 1
    counts["total_lendable"] = counts["on_shelf"] + counts["bound"]
    counts["total_records"] = counts["total_lendable"] + counts["withdrawn"]
    return counts


def _build_explanation(title, slot, units, items, withdrawn) -> list[str]:
    """逐 slot 的判定解释：覆盖单元、编号沿革、实体计入情况。"""
    exp: list[str] = []
    for unit in units:
        cur = unit.current_numbering
        exp.append(
            f"出版单元#{unit.id}「{unit.label}」覆盖本期"
            f"（当前编号 {_fmt_assignment(cur)}）" if cur else f"出版单元#{unit.id} 覆盖本期"
        )
        history = [n for n in unit.numberings.all() if n.valid_to is not None]
        for old in history:
            exp.append(
                f"单元#{unit.id} 编号沿革：{_fmt_assignment(old)} → 改号失效于 "
                f"{old.valid_to:%Y-%m-%d}（{old.reason or '出版社更正'}）"
            )
    for item in items:
        loc = item.effective_location
        exp.append(
            f"实体 {item.barcode}（{item.get_status_display()}"
            f"@{loc.code if loc else '—'}）计入可借实体"
        )
    for item in withdrawn:
        exp.append(f"实体 {item.barcode} 已注销，不计入可借实体")
    if not units:
        for old in _historical_assignments_for(title, slot.volume, slot.number):
            exp.append(
                f"出版单元#{old.issue_id} 曾以 {_fmt_assignment(old)} 对应本期，"
                f"已于 {old.valid_to:%Y-%m-%d} 改号为 "
                f"{_fmt_assignment(old.issue.current_numbering)}"
            )
        if not exp:
            exp.append("无任何出版登记覆盖本期")
    if units and not items:
        exp.append("有出版登记但无可借实体 → 判定缺藏")
    return exp


def analyze_title(title, upto: tuple[int, int] | None = None) -> Analysis:
    """逐 slot 判定在藏 / 缺藏 / 缺号，内容覆盖与实体数量分别统计。"""
    slots = expected_slots(title, upto)
    cov = coverage_map(title)
    issues = list(
        title.issues.prefetch_related(
            "numberings", "items__location", "items__bound_volume__location"
        )
    )
    rows: list[SlotRow] = []
    for slot in slots:
        units = cov.get((slot.volume, slot.number), [])
        items, withdrawn = [], []
        for unit in units:
            for item in unit.items.all():
                (withdrawn if item.status == ItemStatus.WITHDRAWN else items).append(item)
        if not units:
            state = NOT_PUBLISHED
        elif items:
            state = HELD
        else:
            state = MISSING
        rows.append(
            SlotRow(
                slot=slot,
                state=state,
                units=units,
                items=items,
                withdrawn_items=withdrawn,
                explanation=_build_explanation(title, slot, units, items, withdrawn),
            )
        )
    supplements = [i for i in issues if i.kind == IssueKind.SUPPLEMENT]
    redundancies = [
        {"year": r.slot.year, "month": r.slot.month, "volume": r.slot.volume,
         "number": r.slot.number, "issue_ids": [u.id for u in r.units],
         "labels": [u.label for u in r.units]}
        for r in rows if r.redundant
    ]
    return Analysis(
        title=title,
        rows=rows,
        supplements=supplements,
        redundancies=redundancies,
        collisions=_numbering_collisions(title),
        title_notes=_title_notes(title),
        entity_stats=_entity_stats(title),
    )


def verification_hint(title, row: SlotRow) -> str:
    """缺藏 / 缺号的逐项核实提示。"""
    s = row.slot
    if row.state == MISSING:
        unit_desc = "、".join(f"#{u.id}「{u.label}」" for u in row.units)
        return (
            f"第{s.volume}卷第{s.number}期（{s.year}年{s.month}月）已有出版登记（单元{unit_desc}），"
            f"但无可借实体。请逐项核对：1) 采购与登到记录；2) 架位与在途；3) 是否尚在装订车间。"
        )
    base = (
        f"按《{title.name}》枚举规则，{s.year}年{s.month}月应有第{s.volume}卷第{s.number}期，"
        f"但无出版登记。缺号不等于缺藏：请与出版方核实该期是否出版"
        f"（可能休刊、改号、或应以合期/增刊形式登记）。"
    )
    moved = [e for e in row.explanation if "改号为" in e]
    if moved:
        base += " " + "；".join(moved)
    return base
