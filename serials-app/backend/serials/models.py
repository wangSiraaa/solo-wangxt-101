"""连续出版物登记数据模型。

分层表达两类关系：
  * 内容层：Title（刊名，含沿革） -> Issue（期，发行年月与卷期编号分开，
    一期合刊可覆盖多个期号）。
  * 实体层：Item（册，一刊多册各自成行、唯一条码） -> BoundVolume（合订本，
    合订不抹掉子期，拆订逐册恢复位置）。
所有入藏 / 移库 / 合订 / 拆订都写入 OperationLog，历史可在容器中复现。
"""
from django.core.exceptions import ValidationError
from django.db import models


# ---------------------------------------------------------------- 枚举规则

class Frequency(models.TextChoices):
    MONTHLY = "MONTHLY", "月刊"
    BIMONTHLY = "BIMONTHLY", "双月刊"
    QUARTERLY = "QUARTERLY", "季刊"
    SEMIANNUAL = "SEMIANNUAL", "半年刊"
    ANNUAL = "ANNUAL", "年刊"


#: 每种频率相邻两期之间相隔的月数
FREQUENCY_STEP_MONTHS = {
    Frequency.MONTHLY: 1,
    Frequency.BIMONTHLY: 2,
    Frequency.QUARTERLY: 3,
    Frequency.SEMIANNUAL: 6,
    Frequency.ANNUAL: 12,
}


class TitleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "在版"
    CEASED = "CEASED", "停刊"


class IssueKind(models.TextChoices):
    REGULAR = "REGULAR", "正期"
    SUPPLEMENT = "SUPPLEMENT", "增刊"
    COMBINED = "COMBINED", "合期"  # 一期物理合刊，覆盖多个期号


class ItemStatus(models.TextChoices):
    ON_SHELF = "ON_SHELF", "在架"
    BOUND = "BOUND", "已装订"


class BoundVolumeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "在订"
    UNBOUND = "UNBOUND", "已拆订"


class OperationType(models.TextChoices):
    CHECK_IN = "CHECK_IN", "入藏"
    BIND = "BIND", "合订"
    UNBIND = "UNBIND", "拆订"
    MOVE_ITEM = "MOVE_ITEM", "册移库"
    MOVE_VOLUME = "MOVE_VOLUME", "合订本移库"
    ISSUE_REGISTER = "ISSUE_REGISTER", "期登记"
    TITLE_CEASE = "TITLE_CEASE", "停刊登记"


# ---------------------------------------------------------------- 刊名与规则

class Title(models.Model):
    """刊名（连续出版物）。沿革通过 predecessor 链表达。"""

    name = models.CharField("刊名", max_length=200)
    issn = models.CharField("ISSN", max_length=9, blank=True, default="")
    frequency = models.CharField(
        "出版频率", max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    start_year = models.PositiveIntegerField("创刊年")
    start_month = models.PositiveSmallIntegerField("创刊月", default=1)

    # 卷期规则：与发行年月分离。卷可跨年（如每年7月起卷，跨年卷）。
    volume_start_number = models.PositiveIntegerField("起始卷号", default=1)
    volume_start_year = models.PositiveIntegerField("首卷起始年")
    volume_start_month = models.PositiveSmallIntegerField("首卷起始月", default=1)
    months_per_volume = models.PositiveSmallIntegerField("每卷跨越月数", default=12)

    status = models.CharField(
        "出版状态", max_length=10, choices=TitleStatus.choices, default=TitleStatus.ACTIVE
    )
    # 停刊年月 = 最后一期的发行年月；之后的月份不再产生应到 slot
    ceased_year = models.PositiveIntegerField("停刊年", null=True, blank=True)
    ceased_month = models.PositiveSmallIntegerField("停刊月", null=True, blank=True)

    predecessor = models.ForeignKey(
        "self",
        verbose_name="前身刊",
        null=True,
        blank=True,
        related_name="successors",
        on_delete=models.SET_NULL,
    )
    note = models.CharField("备注", max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    def clean(self):
        if not 1 <= self.start_month <= 12:
            raise ValidationError({"start_month": "创刊月须在 1-12 之间"})
        if not 1 <= self.volume_start_month <= 12:
            raise ValidationError({"volume_start_month": "首卷起始月须在 1-12 之间"})
        if self.status == TitleStatus.CEASED:
            if not self.ceased_year or not self.ceased_month:
                raise ValidationError("停刊刊名必须登记停刊年月")
            if not 1 <= self.ceased_month <= 12:
                raise ValidationError({"ceased_month": "停刊月须在 1-12 之间"})
        if self.predecessor_id and self.predecessor_id == self.pk:
            raise ValidationError({"predecessor": "前身刊不能是自身"})


class Location(models.Model):
    code = models.CharField("位置代码", max_length=32, unique=True)
    name = models.CharField("位置名称", max_length=100)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


# ---------------------------------------------------------------- 内容层：期

class Issue(models.Model):
    """期（书目层）。发行年月与卷期编号分开记录。

    合期：kind=COMBINED，number..number_end 覆盖多个期号；
    增刊：kind=SUPPLEMENT，supplement_no 为增刊序号，不占正期 slot。
    """

    title = models.ForeignKey(Title, verbose_name="刊名", related_name="issues", on_delete=models.CASCADE)
    kind = models.CharField(
        "期类型", max_length=12, choices=IssueKind.choices, default=IssueKind.REGULAR
    )
    # 发行年月（与卷期编号分离）
    pub_year = models.PositiveIntegerField("发行年")
    pub_month = models.PositiveSmallIntegerField("发行月")
    # 卷期编号
    volume = models.PositiveIntegerField("卷", null=True, blank=True)
    number = models.PositiveIntegerField("期号（起）", null=True, blank=True)
    number_end = models.PositiveIntegerField("期号（止，仅合期）", null=True, blank=True)
    supplement_no = models.PositiveSmallIntegerField("增刊序号", default=0)
    # 入藏计数器：check_in 以 UPDATE 首语句原子递增，生成期内唯一复本号
    copies_checked_in = models.PositiveIntegerField("累计入藏册数", default=0)
    note = models.CharField("备注", max_length=300, blank=True, default="")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pub_year", "pub_month", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["title", "kind", "volume", "number", "number_end", "supplement_no"],
                name="uniq_issue_identity",
            )
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        base = f"{self.pub_year}年{self.pub_month}月"
        if self.kind == IssueKind.SUPPLEMENT:
            return f"{self.title.name} {base} 增刊{self.supplement_no}"
        if self.kind == IssueKind.COMBINED:
            return f"{self.title.name} {base} 第{self.volume}卷 第{self.number}-{self.number_end}期（合刊）"
        return f"{self.title.name} {base} 第{self.volume}卷 第{self.number}期"

    def clean(self):
        if not 1 <= self.pub_month <= 12:
            raise ValidationError({"pub_month": "发行月须在 1-12 之间"})
        if self.kind == IssueKind.COMBINED:
            if self.volume is None or self.number is None or self.number_end is None:
                raise ValidationError("合期必须登记卷、起期号与止期号")
            if self.number_end <= self.number:
                raise ValidationError({"number_end": "合期止号必须大于起号"})
        else:
            if self.number_end is not None:
                raise ValidationError({"number_end": "非合期不应填写止期号"})
        if self.kind == IssueKind.SUPPLEMENT:
            if self.supplement_no < 1:
                raise ValidationError({"supplement_no": "增刊必须登记增刊序号（>=1）"})
        else:
            if self.volume is None or self.number is None:
                raise ValidationError("正期/合期必须登记卷期编号")
        title = self.title
        if title.status == TitleStatus.CEASED and title.ceased_year:
            if (self.pub_year, self.pub_month) > (title.ceased_year, title.ceased_month):
                raise ValidationError(
                    f"该刊已于 {title.ceased_year}年{title.ceased_month}月 停刊，之后不应有新期"
                )


# ---------------------------------------------------------------- 实体层：册

class Item(models.Model):
    """册（实体）。同一期的两册是不同实体：各自成行、唯一条码、复本号区分，
    任何操作都按条码逐册进行，绝不合并或互相覆盖。"""

    issue = models.ForeignKey(Issue, verbose_name="所属期", related_name="items", on_delete=models.PROTECT)
    barcode = models.CharField("条码", max_length=64, unique=True)
    copy_no = models.PositiveIntegerField("复本号")
    location = models.ForeignKey(Location, verbose_name="当前位置", on_delete=models.PROTECT)
    status = models.CharField(
        "状态", max_length=10, choices=ItemStatus.choices, default=ItemStatus.ON_SHELF
    )
    # 当前所在的合订本（仅 status=BOUND 时有值；历史上订过的记录在 BoundVolumeItem）
    bound_volume = models.ForeignKey(
        "BoundVolume",
        verbose_name="所在合订本",
        null=True,
        blank=True,
        related_name="current_items",
        on_delete=models.SET_NULL,
    )
    checked_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["issue_id", "copy_no"]
        constraints = [
            models.UniqueConstraint(fields=["issue", "copy_no"], name="uniq_item_issue_copy"),
        ]

    def __str__(self):
        return f"{self.barcode}（{self.issue.label} 复本{self.copy_no}）"

    @property
    def effective_location(self):
        """实际所在位置：已装订的册随合订本走。"""
        if self.status == ItemStatus.BOUND and self.bound_volume_id:
            return self.bound_volume.location
        return self.location


class BoundVolume(models.Model):
    title = models.ForeignKey(
        Title, verbose_name="刊名", related_name="bound_volumes", on_delete=models.PROTECT
    )
    barcode = models.CharField("合订本条码", max_length=64, unique=True)
    label = models.CharField("合订本题名", max_length=200)
    location = models.ForeignKey(Location, verbose_name="当前位置", on_delete=models.PROTECT)
    status = models.CharField(
        "状态", max_length=10, choices=BoundVolumeStatus.choices, default=BoundVolumeStatus.ACTIVE
    )
    created_at = models.DateTimeField("装订时间", auto_now_add=True)
    unbound_at = models.DateTimeField("拆订时间", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.barcode} {self.label}"


class BoundVolumeItem(models.Model):
    """合订成员关系。pre_* 字段冻结装订前状态，拆订时逐册恢复（不是只改一个条码）。"""

    bound_volume = models.ForeignKey(
        BoundVolume, verbose_name="合订本", related_name="bound_items", on_delete=models.CASCADE
    )
    item = models.ForeignKey(Item, verbose_name="册", related_name="binding_records", on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField("册序")
    pre_location = models.ForeignKey(Location, verbose_name="装订前位置", on_delete=models.PROTECT)
    pre_status = models.CharField("装订前状态", max_length=10, choices=ItemStatus.choices)
    bound_at = models.DateTimeField(auto_now_add=True)
    unbound_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["bound_volume_id", "position"]
        constraints = [
            models.UniqueConstraint(fields=["bound_volume", "item"], name="uniq_bv_item"),
            models.UniqueConstraint(fields=["bound_volume", "position"], name="uniq_bv_position"),
        ]


# ---------------------------------------------------------------- 操作历史

class OperationLog(models.Model):
    """全部馆藏操作历史：入藏 / 移库 / 合订 / 拆订 / 期登记 / 停刊登记。"""

    type = models.CharField("操作类型", max_length=20, choices=OperationType.choices)
    actor = models.CharField("操作人", max_length=64, default="system")
    title = models.ForeignKey(Title, null=True, blank=True, on_delete=models.SET_NULL)
    issue = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.SET_NULL)
    item = models.ForeignKey(
        Item, null=True, blank=True, related_name="logs", on_delete=models.SET_NULL
    )
    bound_volume = models.ForeignKey(
        BoundVolume, null=True, blank=True, related_name="logs", on_delete=models.SET_NULL
    )
    from_location = models.ForeignKey(
        Location, null=True, blank=True, related_name="+", on_delete=models.SET_NULL
    )
    to_location = models.ForeignKey(
        Location, null=True, blank=True, related_name="+", on_delete=models.SET_NULL
    )
    payload = models.JSONField("明细", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"[{self.get_type_display()}] #{self.pk} {self.created_at:%Y-%m-%d %H:%M}"
