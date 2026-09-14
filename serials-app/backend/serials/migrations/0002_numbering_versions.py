"""卷期编号版本化：Issue.volume/number/number_end 迁入 NumberAssignment。

步骤：建版本表 -> 数据搬迁（每个非增刊单元生成"初始登记"版本） ->
删除旧字段与旧约束 -> 新约束与枚举值。
"""
import django.db.models.deletion
from django.db import migrations, models


def copy_numbering_to_assignments(apps, schema_editor):
    Issue = apps.get_model("serials", "Issue")
    NumberAssignment = apps.get_model("serials", "NumberAssignment")
    for issue in Issue.objects.all().iterator():
        if issue.kind == "SUPPLEMENT":
            continue  # 增刊无卷期编号，不建映射版本
        NumberAssignment.objects.create(
            issue_id=issue.id,
            volume=issue.volume,
            number=issue.number,
            number_end=issue.number_end,
            valid_from=issue.registered_at,
            reason="初始登记",
        )


class Migration(migrations.Migration):

    dependencies = [("serials", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="NumberAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("volume", models.PositiveIntegerField(blank=True, null=True, verbose_name="卷")),
                ("number", models.PositiveIntegerField(blank=True, null=True, verbose_name="期号（起）")),
                ("number_end", models.PositiveIntegerField(blank=True, null=True, verbose_name="期号（止，仅合期）")),
                ("valid_from", models.DateTimeField(verbose_name="生效时间")),
                ("valid_to", models.DateTimeField(blank=True, null=True, verbose_name="失效时间")),
                ("reason", models.CharField(blank=True, default="", max_length=200, verbose_name="改号原因")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="numberings",
                        to="serials.issue",
                        verbose_name="出版单元",
                    ),
                ),
            ],
            options={"ordering": ["issue_id", "valid_from", "id"]},
        ),
        migrations.AddConstraint(
            model_name="numberassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(valid_to__isnull=True),
                fields=("issue",),
                name="uniq_current_numbering",
            ),
        ),
        migrations.RunPython(copy_numbering_to_assignments, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="issue", name="uniq_issue_identity"),
        migrations.RemoveField(model_name="issue", name="volume"),
        migrations.RemoveField(model_name="issue", name="number"),
        migrations.RemoveField(model_name="issue", name="number_end"),
        migrations.AddConstraint(
            model_name="issue",
            constraint=models.UniqueConstraint(
                fields=("title", "kind", "pub_year", "pub_month", "supplement_no"),
                name="uniq_issue_identity",
            ),
        ),
        migrations.AlterField(
            model_name="item",
            name="status",
            field=models.CharField(
                choices=[("ON_SHELF", "在架"), ("BOUND", "已装订"), ("WITHDRAWN", "已注销")],
                default="ON_SHELF",
                max_length=10,
                verbose_name="状态",
            ),
        ),
        migrations.AlterField(
            model_name="boundvolumeitem",
            name="pre_status",
            field=models.CharField(
                choices=[("ON_SHELF", "在架"), ("BOUND", "已装订"), ("WITHDRAWN", "已注销")],
                max_length=10,
                verbose_name="装订前状态",
            ),
        ),
        migrations.AlterField(
            model_name="operationlog",
            name="type",
            field=models.CharField(
                choices=[
                    ("CHECK_IN", "入藏"), ("BIND", "合订"), ("UNBIND", "拆订"),
                    ("MOVE_ITEM", "册移库"), ("MOVE_VOLUME", "合订本移库"),
                    ("ISSUE_REGISTER", "期登记"), ("TITLE_CEASE", "停刊登记"),
                    ("RENUMBER", "改号"), ("TITLE_RESUME", "停刊更正"),
                    ("SPLIT_VOLUME", "合订册拆分"), ("WITHDRAW_ITEM", "实体注销"),
                ],
                max_length=20,
                verbose_name="操作类型",
            ),
        ),
    ]
