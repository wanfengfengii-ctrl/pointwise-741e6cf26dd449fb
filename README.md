# 耐久试验离线疲劳复核台

模拟零部件耐久试验室接收单轴台架载荷。白班按台架原拍校对和冻结班账，夜班在采样库关闭后按实收件签发整卷疲劳账，复测负责人用完整循环的两个原拍定位复测区段。

## 运行

需要 Python 3.11，使用标准库和本地 SQLite。控制台物化工程时提供 `check_project.py`。在工程根目录执行完整回归：

```sh
python3 -B check_project.py
```

同一套测试也可直接发现：

```sh
python3 -B -m unittest discover -s tests -t .
```

使用两份有限样例重放勘误和断源签发：

```sh
python3 -B -m unittest tests.test_history.HistoryTests.test_correct_and_reopen
```

演示在临时目录创建站库和中心库，分别关闭站库后签发旧账和勘误账，再重开中心按原号领取两份定稿。`POINTWISE_SCENARIO` 记录含输入、独立手算预期、实算账和原件及回执反查结果。原样例的完整循环幅差为 2 kN，归第 2、5 拍，另有一个幅差 6 kN 的半循环。更正第 4、6 拍后，幅差 2、4、6 kN 各有一个半循环。

## 业务和接口

| 步骤 | 调用及结果 |
| --- | --- |
| 1. 台架采录 | `source.record.record_measurements(measurements, specimen, rows)` 保存有序 `(原拍, kN)` 批次，返回原测修订号。 |
| 2. 白班冻结 | `shift.revision.freeze_shift(measurements, shifts, specimen, measurement_id, first, last)` 核对指定闭区间覆盖并返回 `FrozenShift`，内含冻结号及班内账。 |
| 3. 固定件交接 | `evidence.issuer.issue_evidence(measurements, shifts, archive, shift_id)` 返回 V1 JSON 文本。补发读取存档原件。 |
| 4. 夜班实收 | `intake.accept.accept_evidence(catalog, original)` 验件并登记，返回实收号，同件重投仍用原号。 |
| 5. 断源选件 | 关闭站端连接，将同一试件的实收号按请求原序连成连续区间。显式选择可以跨原测修订。 |
| 6. 整卷签发 | `report.assemble.assemble_report(catalog, reports, receipt_ids)` 返回 `PublishedReport`，包含疲劳账、端点、有序出处、实际父件和签发回执。 |
| 7. 原测勘误 | `source.correction.correct_measurements(measurements, specimen, parent_id, changes)` 按指定父修订更正已有原拍的读值，返回新修订号。旧快照及冻结绑定继续按旧号领取。 |
| 8. 签发勘误账 | 另冻另发，明确按新实收号与仍适用的班件签发新定稿。 |
| 9. 历史领取 | `report.publication.get_report(reports, catalog, report_id)` 领取原定稿、原父件及回执。未知号返回 `None`。 |

站库连接用于 `MeasurementRepository`、`ShiftRepository` 和 `EvidenceArchive`，按此顺序调用 `initialize()`。中心库使用另一个连接，`ReceiptCatalog` 与 `ReportRepository` 共用此中心连接，分别调用 `initialize()`。连接使用 `sqlite3.connect()` 的默认事务模式并开启 `PRAGMA foreign_keys = ON`。公开写入口调用前连接须空闲，由入口管理事务。初始化补建结构，保留已有数据、勘误和成果，样例仅由测试及演示装入临时库。

## 口径与错误

原拍是正整数，保持原序和编号。载荷使用 `Fraction`、整数或能解析为有理数的文本，例如 `4/3` 或 `0.25`，单位为 kN。无效值、空批次、重复拍和逆序拍整批引发 `ValueError`。采录保留物理缺拍，冻结和选件分别在自己的边界拒绝缺拍。未知冻结号、错试件、声明冲突、非法范围或无效选件均引发 `ValueError`，无相应新增记录。持久化异常在回滚后传回调用方。

V1 外层含 `version`、`piece_id`、`shift_id`、`measurement_id`、`coverage` 及 `body`。`body` 是带来源与覆盖的精确 JSON 文本，`piece_id` 绑定其 UTF-8 内容。正文传递班内候选首末、反转和平台首达原拍。逐拍原测保存在站库。中心先核对来源和覆盖，再按实际选件恢复整卷核定点。

连续等值平台折成一点，归整个平台的首达原拍。核定点是首末及方向反转处。从左起找首个满足中间幅差不大于两侧相邻幅差的四点窗口，计一个完整循环，记录中间两点的原拍并移除这两点，重新从左检查。剩余相邻点各计一个半循环。幅差按精确有理值分组，分别给出完整次数和半循环个数。单拍及全等值卷产出空账。单班账按该班独立结算，签发整卷账时用整卷核定点重新计算。

签发事务共同写入账、出处和签发回执，成功提交后返回。回归覆盖写报告后、提交前中断和重开重试。完整回归还覆盖精确载荷回读、整批拒绝、固定件补发、同范围新旧件、切班位置与平台归责、选件拒绝、旧号领取以及重复初始化。
