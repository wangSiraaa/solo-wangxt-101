# 连续出版物登记系统

刊名沿革、卷期枚举、编号版本、入藏 / 合订 / 拆订 / 移库一体化登记应用。

- **前端**：Vue 3 + Vite —— 时间轴查看内容覆盖与实体实际位置
- **后端**：Django + Django REST Framework —— 入藏、合订、拆订、移库、改号、复刊、拆分、注销
- **数据库**：PostgreSQL —— 刊名沿革、出版单元、编号映射版本、实体及规则

## 快速开始（容器）

```bash
docker compose up --build
```

- 前端：http://localhost:8080 （nginx 托管 Vue 构建产物并反代 `/api`）
- 后端：http://localhost:8000/api/ （首次启动自动迁移并写入演示数据与更正场景）

演示数据分两层：

1. `seed_demo`：**跨年卷**《海洋学报》（每年 7 月起卷，第 37 卷 = 2024-07..2025-06）、
   **停刊月份**《地质季刊》、**两期合刊**《城市水利月刊》2025 年 7-8 期合刊、增刊、
   刊名沿革链（《城市水利通讯》→《城市水利月刊》）、合订 / 拆订 / 移库历史。
2. `seed_corrections`：**改号形成重名**（2025 第9期→第10期，与已有第10期重名）、
   **合订册内改号**（海洋学报 2025-01 由 (37,7) 改为 (38,1)，册序不变）、
   **停刊改为延迟出版**（地质季刊复刊并补登延迟期）、
   **补寄拆合刊**（7-8 合刊之后补寄两本单期，合刊保留待馆员决定）、
   **合订册拆分**（BV-CS-2025-1 拆出第3期另立新册）。

本地开发（无 Docker）：

```bash
cd backend && pip install -r requirements.txt
DB_ENGINE=sqlite python manage.py migrate
DB_ENGINE=sqlite python manage.py seed_demo && DB_ENGINE=sqlite python manage.py seed_corrections
DB_ENGINE=sqlite python manage.py runserver        # :8000
cd frontend && npm install && npm run dev          # :5173，代理 /api 到 :8000
```

运行测试：

```bash
cd backend && DB_ENGINE=sqlite python -m pytest    # 43 个用例
```

## 领域模型

两层关系分开表达：

| 层 | 模型 | 说明 |
| --- | --- | --- |
| 内容层 | `Title` | 刊名。`predecessor` 自引用表达**刊名沿革**；`frequency`、卷规则、`status`（在版/停刊）+ `ceased_year/month` |
| 内容层 | `Issue` | **出版单元（稳定身份）**。发行年月（`pub_year/month`）是固有属性；主键即身份，改号、补寄、合订都不改变它 |
| 内容层 | `NumberAssignment` | **显示编号映射版本**。`valid_to` 为空为当前版本（部分唯一约束保证每单元至多一条）；旧版本保留供检索 |
| 实体层 | `Item` | 册。唯一条码；`(issue, copy_no)` 唯一——同一单元的两册是不同实体 |
| 实体层 | `BoundVolume` + `BoundVolumeItem` | 合订本及成员关系。`position` 为装订顺序；`pre_*` 冻结装订前状态供拆订逐册恢复 |
| 历史 | `OperationLog` | 入藏 / 移库 / 合订 / 拆订 / 期登记 / 改号 / 停刊更正 / 合订册拆分 / 实体注销 |

### 出版单元身份 vs 显示编号（映射版本）

- 出版社改号 = 关闭当前 `NumberAssignment`（置 `valid_to`）+ 新增版本，**单元身份与
  实体记录不变，不会因改号重复生成**。
- **旧编号仍能检索**：`GET /api/lookup/numbering/?title=&volume=&number=[&at=]` 返回全部
  匹配版本（含历史）；加 `at` 时间点可解析"当时持有该编号的单元"——历史目录链接不会
  指向错误实体。改号形成**重名**时，两个单元都列出，各自指向自己的实体。
- 覆盖关系跟随当前编号版本：改号后时间轴与缺藏**自动重算**，原 slot 的缺号解释中会
  注明"单元 #N 曾以……对应本期，已改号为……"。

### 内容覆盖 vs 实体数量（分别统计）

- 一个合刊覆盖两个出版单元 ≠ 两本可借实体。时间轴统计分列：
  `stats.coverage`（应到/在藏/缺藏/缺号，slot 级）与
  `stats.entities`（在架/已装订/已注销/可借合计，册级）。
- **补寄单期**与原合刊并存：同一 slot 被多单元覆盖时标记"冗余待决"，
  **系统不自动删除合刊**；馆员在界面上逐 slot 决定保留或注销多余实体
  （`POST /api/items/{id}/withdraw/`，注销后不计入可借实体）。

### 枚举规则（`serials/rules.py`）

- **应到 slot**：从创刊月起按频率步长生成；卷号按 `volume_start_*` 推算 → 支持跨年卷。
- **合期**：一个物理单元覆盖 `number..number_end` 多个 slot，被覆盖 slot 不算缺号。
- **增刊**：不占正期 slot，单独列出。
- **停刊**：`ceased_year/month` 之后不产生应到 slot；**停刊更正**（实为延迟出版）经
  `POST /api/titles/{id}/resume/` 恢复在版，应到自动重算并在 `title_notes` 留痕。
- **缺号 ≠ 缺藏**：`MISSING`（已出版无可借实体）与 `NOT_PUBLISHED`（无出版登记）分列，
  每个 slot 附**判定解释**（覆盖单元、编号沿革、实体计入情况），可逐项核实。

### 合订册内的编号修订与拆分

- 册内改号：`BoundVolume.index_candidates`（索引候选）按**原装订顺序**列出各册当前
  编号与历史别名——改号后候选自动更新，`position` 不变。
- **合订册拆分**：`POST /api/bound-volumes/{id}/split/` 把部分成员移入新合订本，
  两侧成员均保留原有相对册序；全部拆出请用拆订。

### 并发入藏不合并

`check_in` 事务首语句即 `UPDATE issue SET copies_checked_in = copies_checked_in + 1`
（PostgreSQL 行锁串行化），递增值即复本号；`(issue, copy_no)` 与 `barcode` 唯一约束兜底。
8 线程并发入藏同一单元的测试见 `serials/tests/test_checkin.py`。

## API 一览

| 端点 | 说明 |
| --- | --- |
| `GET /api/titles/` | 刊名列表（含沿革前身） |
| `GET /api/titles/{id}/timeline/` | 时间轴：slot × 单元 × 实体；覆盖/实体双统计；冗余与重名 |
| `GET /api/titles/{id}/gaps/` | 缺藏 / 缺号清单（逐项解释与核实提示） |
| `GET /api/titles/{id}/lineage/` | 刊名沿革链 |
| `POST /api/titles/{id}/resume/` | 停刊更正（实为延迟出版） |
| `GET/POST /api/issues/` | 出版单元登记（`?title=&kind=` 过滤） |
| `POST /api/issues/{id}/renumber/` | 改号（新增映射版本；返回重名告警） |
| `GET /api/issues/{id}/numberings/` | 单元的编号版本历史 |
| `GET /api/lookup/numbering/` | 编号检索（含历史版本，`?title=&volume=&number=&at=`） |
| `POST /api/items/check_in/` | 入藏 `{issue_id, barcode, location_id}` |
| `POST /api/items/{id}/move/` | 册移库 |
| `POST /api/items/{id}/withdraw/` | 实体注销（馆员决定） |
| `GET /api/items/{id}/history/` | 单册操作历史 |
| `POST /api/bound-volumes/bind/` | 合订 `{item_ids, barcode, label, location_id}` |
| `POST /api/bound-volumes/{id}/unbind/` | 拆订（逐册恢复） |
| `POST /api/bound-volumes/{id}/split/` | 合订册拆分（保留相对册序） |
| `POST /api/bound-volumes/{id}/move/` | 合订本移库 |
| `GET /api/logs/` | 操作历史（`?type=&title=&item=&bound_volume=` 过滤） |

## 需求逐项核实

| 需求 | 验证方式 |
| --- | --- |
| 单元身份与显示编号映射版本 | `NumberAssignment` 版本表；`GET /api/issues/{id}/numberings/` |
| 旧编号仍能检索 | `GET /api/lookup/numbering/?title=2&volume=11&number=9`（改号前的旧编号） |
| 实体记录不因改号重复生成 | 测试 `test_renumber_keeps_identity_and_items`：改号前后条码集合不变 |
| 合刊覆盖两单元 ≠ 两本可借实体 | 测试 `test_combined_coverage_is_not_two_entities`；时间轴双统计 |
| 补寄单期到达不自动删合刊 | 测试 `test_supplementary_singles_coexist_with_combined`；前端"多单元覆盖"面板 |
| 馆员选择是否保留合刊 | `POST /api/items/{id}/withdraw/`；测试 `test_librarian_withdraws_combined_after_singles` |
| 册内改号更新索引候选、保留册序 | 测试 `test_renumber_inside_bound_volume_keeps_order`；`index_candidates` |
| 改号形成重名 | 种子 `seed_corrections` 第 1 场景；测试 `test_renumber_collision_creates_duplicate_name` |
| 停刊改为延迟出版 | `POST /api/titles/{id}/resume/`；测试 `test_resume_title_recaculates_gaps` |
| 合订册拆分 | `POST /api/bound-volumes/{id}/split/`；测试 `test_split_bound_volume_preserves_order` |
| 缺藏重新计算可解释 | 每个 slot 的 `explanation`（覆盖单元/编号沿革/实体计入）+ `title_notes` 留痕 |
| 历史目录链接不指向错误实体 | 编号检索按单元身份返回；`at` 时间点解析当时持有者 |
| 发行年月与卷期编号分开 | `Issue.pub_year/month`（固有）与 `NumberAssignment`（版本化显示编号） |
| 缺号 ≠ 缺藏 | `MISSING` 与 `NOT_PUBLISHED` 分列，逐项核实提示 |
| 并发入藏同编号不合并 | 测试 `test_concurrent_checkin_same_issue_not_merged`（8 线程 → 8 实体） |
| 跨年卷 / 停刊月份 / 两期合刊 | 种子样例 + `test_cross_year_volume` / `test_ceased_title_stops_slots` / `test_combined_issue_covers_both_slots` |
| 容器复现移库 / 装订历史 | 启动后 `GET /api/logs/?type=BIND`（或 MOVE_ITEM / SPLIT_VOLUME / RENUMBER 等） |

## 目录结构

```
serials-app/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── config/            # Django 项目设置（PostgreSQL 默认，DB_ENGINE=sqlite 可本地验证）
│   └── serials/
│       ├── models.py      # 刊名沿革 / 出版单元 / 编号版本 / 实体 / 合订 / 操作日志
│       ├── rules.py       # 卷期枚举、多单元覆盖、可解释缺藏分析（纯逻辑）
│       ├── services.py    # 入藏 / 合订 / 拆订 / 移库 / 改号 / 复刊 / 拆分 / 注销
│       ├── views.py       # DRF 视图 + 编号检索
│       ├── management/commands/seed_demo.py
│       ├── management/commands/seed_corrections.py
│       └── tests/         # 43 个 pytest 用例
└── frontend/
    ├── Dockerfile         # 构建产物交给 nginx
    ├── nginx.conf         # 静态托管 + /api 反代
    └── src/
        ├── App.vue
        └── components/    # 时间轴 / 单元抽屉 / 缺藏清单 / 冗余面板 / 操作历史
                           # 入藏·合订·拆订·拆分·移库·改号·编号检索 对话框
```
