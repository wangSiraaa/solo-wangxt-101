"""演示数据：跨年卷、停刊月份、两期合刊、刊名沿革、缺藏/缺号对照。

所有馆藏操作都走 services 层，因此 OperationLog 里会完整复现
入藏 / 移库 / 合订 / 拆订历史（容器内 `python manage.py seed_demo` 即可重放）。

用法：python manage.py seed_demo [--flush]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from serials import services
from serials.models import (
    Frequency,
    IssueKind,
    Location,
    Title,
    TitleStatus,
)

ACTOR = "seed"


class Command(BaseCommand):
    help = "写入连续出版物演示数据（跨年卷 / 停刊 / 合期 / 沿革 / 装订移库历史）"

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="先清空业务表再写入")

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()
        elif Title.objects.exists():
            self.stdout.write("已有数据，跳过（可用 --flush 重建）")
            return
        with transaction.atomic():
            self._run()

    # ------------------------------------------------------------ 数据

    def _flush(self):
        from serials.models import BoundVolume, BoundVolumeItem, Issue, Item, OperationLog
        OperationLog.objects.all().delete()
        BoundVolumeItem.objects.all().delete()
        BoundVolume.objects.all().delete()
        Item.objects.all().delete()
        Issue.objects.all().delete()
        Title.objects.all().delete()
        Location.objects.all().delete()
        self.stdout.write("已清空业务表")

    def _run(self):
        # 位置
        loc_xk, _ = Location.objects.get_or_create(code="XK-1F", defaults={"name": "一层现刊阅览区"})
        loc_gk, _ = Location.objects.get_or_create(code="GK-2F", defaults={"name": "二层过刊库"})
        loc_mj, _ = Location.objects.get_or_create(code="MJ-B1", defaults={"name": "地下密集书库"})

        # ---- 刊名沿革：前身《城市水利通讯》(2015-01 创刊, 2023-12 停刊)
        pred, _ = Title.objects.get_or_create(
            name="城市水利通讯",
            defaults=dict(
                issn="1000-0001", frequency=Frequency.MONTHLY,
                start_year=2015, start_month=1,
                volume_start_number=1, volume_start_year=2015, volume_start_month=1,
                months_per_volume=12,
                status=TitleStatus.CEASED, ceased_year=2023, ceased_month=12,
                note="2024年起更名为《城市水利月刊》",
            ),
        )
        # ---- 本刊《城市水利月刊》：卷号接续前身（首卷=第10卷）
        main, _ = Title.objects.get_or_create(
            name="城市水利月刊",
            defaults=dict(
                issn="1000-0002", frequency=Frequency.MONTHLY,
                start_year=2024, start_month=1,
                volume_start_number=10, volume_start_year=2024, volume_start_month=1,
                months_per_volume=12,
                status=TitleStatus.ACTIVE,
                predecessor=pred,
                note="由《城市水利通讯》更名而来，卷号延续",
            ),
        )

        # ---- 跨年卷样例：《海洋学报》每年7月起卷，第37卷=2024-07..2025-06
        ocean, _ = Title.objects.get_or_create(
            name="海洋学报",
            defaults=dict(
                issn="1000-0003", frequency=Frequency.MONTHLY,
                start_year=2023, start_month=7,
                volume_start_number=36, volume_start_year=2023, volume_start_month=7,
                months_per_volume=12,
                status=TitleStatus.ACTIVE,
                note="跨年卷：每卷覆盖当年7月至次年6月",
            ),
        )

        # ---- 停刊月份样例：《地质季刊》2025年第2期（2025-04）后停刊
        geo, _ = Title.objects.get_or_create(
            name="地质季刊",
            defaults=dict(
                issn="1000-0004", frequency=Frequency.QUARTERLY,
                start_year=2020, start_month=1,
                volume_start_number=1, volume_start_year=2020, volume_start_month=1,
                months_per_volume=12,
                status=TitleStatus.CEASED, ceased_year=2025, ceased_month=4,
                note="2025年第2期后停刊，此后月份不产生应到",
            ),
        )

        # ================= 《城市水利月刊》出版登记 =================
        def reg(title, **kw):
            return services.register_issue(actor=ACTOR, title=title, **kw)

        # 2024 年：第10卷。缺 no.5 的实体（缺藏）；no.11 不登记（缺号）。
        issues_2024 = {}
        for n in range(1, 13):
            if n == 11:
                continue  # 缺号：无出版登记
            issues_2024[n] = reg(title=main, kind=IssueKind.REGULAR,
                                 pub_year=2024, pub_month=n, volume=10, number=n)
        # 2025 年：第11卷。7-8 月为两期合刊；5 月有增刊；no.10 缺藏；11、12 缺号。
        issues_2025 = {}
        for n in range(1, 11):
            if n == 7:
                continue
            if n == 8:
                continue
            issues_2025[n] = reg(title=main, kind=IssueKind.REGULAR,
                                 pub_year=2025, pub_month=n, volume=11, number=n)
        combined = reg(title=main, kind=IssueKind.COMBINED,
                       pub_year=2025, pub_month=7, volume=11, number=7, number_end=8,
                       note="暑期两期合刊")
        supp = reg(title=main, kind=IssueKind.SUPPLEMENT,
                   pub_year=2025, pub_month=5, volume=None, number=None,
                   supplement_no=1, note="城市防洪专刊")
        # 2026 年：第12卷，登记 1-3 月
        issues_2026 = {n: reg(title=main, kind=IssueKind.REGULAR,
                              pub_year=2026, pub_month=n, volume=12, number=n)
                       for n in range(1, 4)}

        # ================= 入藏 =================
        def cin(issue, barcode, loc):
            return services.check_in(issue_id=issue.id, barcode=barcode,
                                     location_id=loc.id, actor=ACTOR)

        # 2024：no.5 故意不入藏 -> 缺藏
        items_2024 = {}
        for n, issue in issues_2024.items():
            if n == 5:
                continue
            items_2024[n] = cin(issue, f"CS-2024-{n:02d}", loc_gk)
        # 2025：1-6、9 入藏；no.10 不入藏 -> 缺藏
        items_2025 = {}
        for n, issue in issues_2025.items():
            if n == 10:
                continue
            items_2025[n] = cin(issue, f"CS-2025-{n:02d}", loc_xk)
        # 两期合刊入藏两册：同编号、不同实体、不同条码
        cin(combined, "CS-2025-78A", loc_xk)
        cin(combined, "CS-2025-78B", loc_xk)
        # 增刊入藏一册
        cin(supp, "CS-2025-S1", loc_xk)
        # 2026：1-3 入藏现刊区
        for n, issue in issues_2026.items():
            cin(issue, f"CS-2026-{n:02d}", loc_xk)

        # ================= 移库历史 =================
        services.move_item(item_id=items_2025[9].id, to_location_id=loc_gk.id, actor=ACTOR)

        # ================= 合订 + 移库 + 拆订历史 =================
        # 2025 年 1-3 期合订 -> 入过刊库 -> 再移密集书库
        bv1 = services.bind_items(
            item_ids=[items_2025[1].id, items_2025[2].id, items_2025[3].id],
            barcode="BV-CS-2025-1", label="城市水利月刊 2025年1-3期合订本",
            location_id=loc_gk.id, actor=ACTOR,
        )
        services.move_bound_volume(bound_volume_id=bv1.id, to_location_id=loc_mj.id, actor=ACTOR)

        # 2024 年 1-3 期合订后又拆订：三册装订前位置不同，拆订须逐册恢复
        services.move_item(item_id=items_2024[2].id, to_location_id=loc_xk.id, actor=ACTOR)
        services.move_item(item_id=items_2024[3].id, to_location_id=loc_mj.id, actor=ACTOR)
        bv2 = services.bind_items(
            item_ids=[items_2024[1].id, items_2024[2].id, items_2024[3].id],
            barcode="BV-CS-2024-1", label="城市水利月刊 2024年1-3期合订本",
            location_id=loc_gk.id, actor=ACTOR,
        )
        services.unbind(bound_volume_id=bv2.id, actor=ACTOR)

        # ================= 《海洋学报》（跨年卷） =================
        # 第37卷 = 2024-07 .. 2025-06；登记并入藏 2024-07..2024-12
        for i, (y, m) in enumerate([(2024, 7), (2024, 8), (2024, 9), (2024, 10), (2024, 11), (2024, 12)], start=1):
            iss = reg(title=ocean, kind=IssueKind.REGULAR, pub_year=y, pub_month=m,
                      volume=37, number=i)
            cin(iss, f"HY-{y}-{m:02d}", loc_gk)
        # 2025 上半年（第37卷 7-12期）登记但 2025-03 不入藏 -> 缺藏
        for i, (y, m) in enumerate([(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2025, 5), (2025, 6)], start=7):
            iss = reg(title=ocean, kind=IssueKind.REGULAR, pub_year=y, pub_month=m,
                      volume=37, number=i)
            if m != 3:
                cin(iss, f"HY-{y}-{m:02d}", loc_gk)

        # ================= 《地质季刊》（停刊） =================
        # 2024 全年 + 2025 年 Q1、Q2（2025-04 后停刊）
        for y, q_months in ((2024, [1, 4, 7, 10]), (2025, [1, 4])):
            vol = 5 if y == 2024 else 6
            for idx, m in enumerate(q_months, start=1):
                number = idx if y == 2025 else [1, 4, 7, 10].index(m) + 1
                iss = reg(title=geo, kind=IssueKind.REGULAR, pub_year=y, pub_month=m,
                          volume=vol, number=number)
                cin(iss, f"DZ-{y}-Q{(m + 2) // 3}", loc_gk)

        self.stdout.write(self.style.SUCCESS(
            "演示数据完成：4 个刊名（含沿革链）、跨年卷《海洋学报》、"
            "停刊《地质季刊》(2025-04)、两期合刊 2025(7-8)、增刊、"
            "合订/拆订/移库历史已写入 OperationLog。"
        ))
