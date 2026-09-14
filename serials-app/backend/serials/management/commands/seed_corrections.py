"""更正场景演示数据（在 seed_demo 基础上叠加）：

  1. 改号形成重名：城市水利月刊 2025 年第9期 → 更正为第10期（与已有的第10期重名）。
  2. 合订册内改号：海洋学报 2025 年 1/2/4 期合订后，2025-01 由 (37,7) 更正为 (38,1)。
  3. 停刊改为延迟出版：地质季刊 复刊，并补登延迟出版的 2025 年第3期。
  4. 补寄拆合刊：2025(7-8) 合刊之后补寄两本单期，合刊保留（馆员决定，不自动删）。
  5. 合订册拆分：BV-CS-2025-1 拆出 2025 年第3期，另立新册。

用法：python manage.py seed_corrections   （幂等：已执行则跳过）
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from serials import services
from serials.models import (
    BoundVolume,
    Issue,
    IssueKind,
    Item,
    Location,
    OperationLog,
    OperationType,
    Title,
)

ACTOR = "correction-seed"
MARKER = "seed_corrections_done"


class Command(BaseCommand):
    help = "写入编号更正/补寄/复刊/拆分演示数据（需先执行 seed_demo）"

    def handle(self, *args, **options):
        if OperationLog.objects.filter(payload__marker=MARKER).exists():
            self.stdout.write("更正场景已写入过，跳过")
            return
        if not Title.objects.exists():
            self.stdout.write(self.style.ERROR("请先执行 python manage.py seed_demo"))
            return
        with transaction.atomic():
            self._run()
            OperationLog.objects.create(
                type=OperationType.ISSUE_REGISTER, actor=ACTOR,
                payload={"marker": MARKER},
            )
        self.stdout.write(self.style.SUCCESS("更正场景数据完成"))

    # ------------------------------------------------------------ 工具

    def _issue(self, title, volume, number):
        return Issue.objects.get(
            title=title,
            numberings__volume=volume,
            numberings__number=number,
            numberings__valid_to__isnull=True,
        )

    def _item(self, barcode):
        return Item.objects.get(barcode=barcode)

    # ------------------------------------------------------------ 场景

    def _run(self):
        main = Title.objects.get(name="城市水利月刊")
        ocean = Title.objects.get(name="海洋学报")
        geo = Title.objects.get(name="地质季刊")
        gk = Location.objects.get(code="GK-2F")
        xk = Location.objects.get(code="XK-1F")

        # 1) 改号形成重名：2025 第9期 → 第10期（与原有第10期重名）
        issue9 = self._issue(main, 11, 9)
        services.renumber_issue(
            issue_id=issue9.id, volume=11, number=10,
            reason="出版社更正：2025年第9期应为第10期", actor=ACTOR,
        )

        # 2) 合订册内改号：海洋学报 2025-01/02/04 合订，2025-01 改号 (37,7)→(38,1)
        hy_items = [self._item(f"HY-2025-{m:02d}") for m in (1, 2, 4)]
        services.bind_items(
            item_ids=[it.id for it in hy_items],
            barcode="BV-HY-2025-1", label="海洋学报 2025年部分期合订本",
            location_id=gk.id, actor=ACTOR,
        )
        hy1 = self._issue(ocean, 37, 7)
        services.renumber_issue(
            issue_id=hy1.id, volume=38, number=1,
            reason="出版社调整卷划分：原第37卷第7期改为第38卷第1期", actor=ACTOR,
        )

        # 3) 停停刊更正：地质季刊实为延迟出版；补登 2025 年第3期（2025-07）
        services.resume_title(
            title_id=geo.id, note="出版社确认系延迟出版，非停刊", actor=ACTOR,
        )
        geo.refresh_from_db()
        delayed = services.register_issue(
            title=geo, kind=IssueKind.REGULAR, pub_year=2025, pub_month=7,
            volume=6, number=3, note="延迟出版的2025年第3期",
        )
        services.check_in(issue_id=delayed.id, barcode="DZ-2025-Q3",
                          location_id=gk.id, actor=ACTOR)

        # 4) 补寄拆合刊：2025(7-8) 合刊之后补寄两本单期（合刊保留，冗余待决）
        for n, barcode in ((7, "CS-2025-07S"), (8, "CS-2025-08S")):
            single = services.register_issue(
                title=main, kind=IssueKind.REGULAR, pub_year=2025, pub_month=n,
                volume=11, number=n, note="补寄单期（原7-8合刊拆分）",
            )
            services.check_in(issue_id=single.id, barcode=barcode,
                              location_id=xk.id, actor=ACTOR)

        # 5) 合订册拆分：BV-CS-2025-1 拆出 2025 年第3期
        bv = BoundVolume.objects.get(barcode="BV-CS-2025-1")
        item3 = self._item("CS-2025-03")
        services.split_bound_volume(
            bound_volume_id=bv.id, item_ids=[item3.id],
            new_barcode="BV-CS-2025-2", new_label="城市水利月刊 2025年第3期（拆分）",
            actor=ACTOR,
        )
