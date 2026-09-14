# 连续出版物登记系统

刊名沿革、卷期枚举、入藏 / 合订 / 拆订 / 移库一体化登记应用。

- **前端**：Vue 3 + Vite —— 时间轴查看内容覆盖与实体实际位置
- **后端**：Django + Django REST Framework —— 入藏、合订、拆订、移库
- **数据库**：PostgreSQL —— 刊名沿革、实体、枚举规则与操作历史

## 快速开始（容器）

```bash
docker compose up --build
```

- 前端：http://localhost:8080 （nginx 托管 Vue 构建产物并反代 `/api`）
- 后端：http://localhost:8000/api/ （首次启动自动迁移并写入演示数据）

演示数据包含：**跨年卷**《海洋学报》（每年 7 月起卷，第 37 卷 = 2024-07..2025-06）、
**停刊月份**《地质季刊》（2025-04 后停刊）、**两期合刊**《城市水利月刊》2025 年 7-8 期合刊、
增刊、刊名沿革链（《城市水利通讯》→《城市水利月刊》），以及可复现的合订 / 拆订 / 移库历史。

本地开发（无 Docker）：

```bash
cd backend && pip install -r requirements.txt
DB_ENGINE=sqlite python manage.py migrate && DB_ENGINE=sqlite python manage.py seed_demo
DB_ENGINE=sqlite python manage.py runserver        # :8000
cd frontend && npm install && npm run dev          # :5173，代理 /api 到 :8000
```

运行测试：

```bash
cd backend && DB_ENGINE=sqlite python -m pytest    # 28 个用例
```

## 领域模型

两层关系分开表达：

| 层 | 模型 | 说明 |
| --- | --- | --- |
| 内容层 | `Title` | 刊名。`predecessor` 自引用表达**刊名沿革**；`frequency`、卷规则（`volume_start_*`、`months_per_volume`）、`status`（在版/停刊）+ `ceased_year/month` |
| 内容层 | `Issue` | 期。**发行年月（`pub_year/month`）与卷期编号（`volume/number[/number_end]`）分开**；`kind` 枚举：正期 / 增刊 / 合期 |
| 实体层 | `Item` | 册。唯一条码；`(issue, copy_no)` 唯一——**同一期的两册是不同实体，各自成行** |
| 实体层 | `BoundVolume` + `BoundVolumeItem` | 合订本及成员关系。成员记录冻结装订前位置/状态（`pre_*`），供拆订逐册恢复 |
| 历史 | `OperationLog` | 入藏 / 册移库 / 合订本移库 / 合订 / 拆订 / 期登记 / 停刊登记，含 from→to 位置与明细 payload |

### 枚举规则（`serials/rules.py`）

- **应到 slot**：从创刊月起按频率步长（月刊 1 / 双月 2 / 季刊 3 / 半年 6 / 年 12）生成；
  卷号按 `volume_start_*` 与 `months_per_volume` 推算 → 天然支持**跨年卷**。
- **合期**：一期物理合刊覆盖 `number..number_end` 多个 slot，被覆盖 slot 记为在藏，**不算缺号**。
- **增刊**：不占正期 slot，时间轴上单独标注。
- **停刊**：`ceased_year/month` 之后不再产生应到 slot，也不会被误判缺藏。
- **缺号 ≠ 缺藏**：
  - `MISSING`（缺藏）= 已有出版登记但无任何实体；
  - `NOT_PUBLISHED`（缺号）= 按规则应到但无出版登记（可能休刊、未登记或应以合期登记）。
  - 两者在时间轴与缺藏清单中分开呈现，**逐项附核实提示**。

### 并发入藏不合并

`check_in` 事务首语句即 `UPDATE issue SET copies_checked_in = copies_checked_in + 1`
（PostgreSQL 行锁串行化），递增值即复本号；`(issue, copy_no)` 与 `barcode` 唯一约束兜底，
冲突自动重试。8 线程并发入藏同一期的测试见 `serials/tests/test_checkin.py`。

### 合订与拆订

- **合订**：仅同一刊名、在架的册可合订；册状态改为「已装订」，实际位置随合订本。
  子期详情与时间轴上都能检索到所在合订本及其位置。
- **拆订**：按 `BoundVolumeItem.pre_*` **逐册恢复**各自装订前的位置与状态（不是只覆盖一个条码），
  合订本转为「已拆订」并保留历史。
- **移库**：在架册与在订合订本分别移库；已装订的册禁止单独移库（须随合订本）。

## API 一览

| 端点 | 说明 |
| --- | --- |
| `GET /api/titles/` | 刊名列表（含沿革前身） |
| `GET /api/titles/{id}/timeline/` | 时间轴：应到 slot × 出版登记 × 实体位置 |
| `GET /api/titles/{id}/gaps/` | 缺藏 / 缺号清单（逐项核实提示） |
| `GET /api/titles/{id}/lineage/` | 刊名沿革链 |
| `GET/POST /api/issues/` | 期登记（`?title=` 过滤） |
| `POST /api/items/check_in/` | 入藏 `{issue_id, barcode, location_id}` |
| `POST /api/items/{id}/move/` | 册移库 |
| `GET /api/items/{id}/history/` | 单册操作历史 |
| `POST /api/bound-volumes/bind/` | 合订 `{item_ids, barcode, label, location_id}` |
| `POST /api/bound-volumes/{id}/unbind/` | 拆订（逐册恢复） |
| `POST /api/bound-volumes/{id}/move/` | 合订本移库 |
| `GET /api/logs/` | 操作历史（`?type=&title=&item=&bound_volume=` 过滤） |

## 需求逐项核实

| 需求 | 验证方式 |
| --- | --- |
| 发行年月与卷期编号分开 | `Issue.pub_year/month` 与 `volume/number` 独立字段；时间轴单元格同时展示两者 |
| 增刊 / 合期 / 停刊枚举规则 | `IssueKind`（正期/增刊/合期）+ `TitleStatus`（在版/停刊）；`rules.py` 生成应到 slot |
| 一期合刊覆盖两个期号 | 种子数据 2025(7-8) 合刊；时间轴 7、8 两格均由同一期满足 |
| 两本同一期刊是不同实体 | `Item` 按条码逐行；2025(7-8) 合刊有 `CS-2025-78A/B` 两册 |
| 缺号 ≠ 缺藏 | `GET /api/titles/2/gaps/` 中 `MISSING` 与 `NOT_PUBLISHED` 分列，逐项核实提示 |
| 合订后子期可检索所在册 | `GET /api/issues/{id}/` → `items[].bound_volume` + `effective_location` |
| 拆订恢复对应位置状态 | 种子中 BV-CS-2024-1 拆订后三册各回 XK-1F / MJ-B1；测试 `test_unbind_restores_each_items_own_location` |
| 跨年卷 | 《海洋学报》第 37 卷 = 2024-07..2025-06；测试 `test_cross_year_volume` |
| 停刊月份 | 《地质季刊》2025-04 后无应到 slot；测试 `test_ceased_title_stops_slots` |
| 并发入藏同编号不合并 | 测试 `test_concurrent_checkin_same_issue_not_merged`（8 线程 → 8 实体，复本号 1..8） |
| 容器复现移库 / 装订历史 | 启动后 `GET /api/logs/?type=BIND`（或 MOVE_ITEM / MOVE_VOLUME / UNBIND） |
| 缺藏判断逐项核实 | 前端「缺藏 / 缺号清单」每项附核实提示并可勾选核销 |

## 目录结构

```
serials-app/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── config/            # Django 项目设置（PostgreSQL 默认，DB_ENGINE=sqlite 可本地验证）
│   └── serials/
│       ├── models.py      # 刊名沿革 / 期 / 实体 / 合订 / 操作日志
│       ├── rules.py       # 卷期枚举与缺藏分析（纯逻辑）
│       ├── services.py    # 入藏 / 合订 / 拆订 / 移库（事务 + 日志）
│       ├── views.py       # DRF 视图
│       ├── management/commands/seed_demo.py
│       └── tests/         # 28 个 pytest 用例
└── frontend/
    ├── Dockerfile         # 构建产物交给 nginx
    ├── nginx.conf         # 静态托管 + /api 反代
    └── src/
        ├── App.vue
        └── components/    # 时间轴 / 期详情抽屉 / 缺藏清单 / 操作历史 / 四个操作对话框
```
