# ASR 控制论优化 v3 — 系统性评估报告

## 一、测试结果

| 测试集 | 数量 | 状态 |
|---|---|---|
| 原有测试 | 201 | 全部通过 |
| 新增 v3 优化测试 (test_control_theory_v3.py) | 25 | 全部通过 |
| **总计** | **226** | **全部通过** |

## 二、第一性原理推演

### P0-1: 增量测试

**控制论原理**：反馈延迟 T_delay 与系统稳定性成反比。延迟越小，控制器越能及时做出正确决策。

**实现验证**：
- `_compute_affected_tests()` 基于变更文件名直接对应 + import 依赖扫描
- 每 `incremental_test_interval=3` 轮强制全量测试校准
- Controller 在 `_testing_phase` 中计算 `changed_files` 并注入 `TestStartedEvent.payload`

**自洽性检查**：
- ✅ 增量测试为空时回退到全量测试（`if not affected: test_targets = [str(sandbox)]`）
- ✅ 全量校准周期可配置（`incremental_test_interval`）
- ✅ 变更文件检测基于 `_prev_rollback_entries`（pre-Builder 快照），与已有机制一致

**反事实推演**：
- 假设增量测试漏报（变更影响了未追踪依赖）→ 每 3 轮全量校准会捕获 → circuit breaker 兜底
- 假设 changed_files 为空（第 1 轮无 prev_rollback_entries）→ 跑全量测试 → 正确行为

### P0-2: 执行器前馈控制

**控制论原理**：前馈控制（feedforward）在扰动到达被控对象前进行补偿，减少无效迭代。

**实现验证**：
- `_build_builder_context()` 构建 5 类前馈信号：TRAJECTORY、MODE_HISTORY、REPEATED_FAILURE、BEST_STATE、TREND
- 注入位置：`mode_feedback.insert(0, builder_context)` — Builder 最先看到系统状态

**自洽性检查**：
- ✅ 空历史时返回空字符串，不污染 feedback
- ✅ context 限制在高信号量信息（pass_rate 轨迹、模式历史、重复失败警告），避免 token 浪费
- ✅ 与现有 `[REPAIR_MODE]` feedback 不冲突——context 在前，repair mode 在后

**反事实推演**：
- 假设 Builder session reset → context 包含 BEST_STATE 和 TRAJECTORY → Builder 不会"失忆"
- 假设 context 过长 → 最长约 500 字符（5 条信号 × ~100 字符），可接受

### P1-1: 双传感器交叉验证

**控制论原理**：多传感器融合需要仲裁机制，防止单一传感器噪声误导控制决策。

**实现验证**：
- `_compute_sensor_agreement()` 定义 3 种状态：AGREED、INCOMPLETE_TESTS、TEST_QUALITY_ISSUE
- 仲裁结果存入 `ConvergenceMetrics.sensor_disagreement` 字段
- 不一致时输出 WARN 日志

**自洽性检查**：
- ✅ INCOMPLETE_TESTS（测试通过但功能缺失）→ 不会误导控制器认为已收敛（FINAL_VERIFICATION 会捕获）
- ✅ TEST_QUALITY_ISSUE（测试大面积失败但 Analyzer 认为 OK）→ 提示测试本身可能有问题
- ✅ 仲裁逻辑不干扰主控制回路——仅记录和日志，不直接改变 mode

**反事实推演**：
- 假设 test_pass=1.0 + Analyzer=MISSING → INCOMPLETE_TESTS → FINAL_VERIFICATION 强制 Analyzer 运行 → 正确
- 假设 test_pass=0.3 + Analyzer=ALL_CLEAR → TEST_QUALITY_ISSUE → 日志提示但不改变行为 → 需要人工介入

### P1-2: 自适应限幅

**控制论原理**：变步长控制——初期大步快收敛，后期小步防超调。

**实现验证**：
- `_get_adaptive_limits()` 根据 repair_mode 和 trend streaks 返回 `(max_files, max_lines)`
- OSCILLATION_BREAK: 1/3 限幅；REGRESSION_RECOVERY: 1/4 限幅；improving×2+: 1.5x 放宽；stalled×2+: 1/2 收紧
- `adaptive_limits` 配置开关，可禁用回退到静态值

**自洽性检查**：
- ✅ 与现有 `allow_large_patch_in_initial`（第 1 轮允许大 patch）不冲突——adaptive 在第 2 轮起生效
- ✅ 拒绝消息包含 `(mode={self._repair_mode})` 让 Builder 知道为什么限幅更紧

**反事实推演**：
- 假设 OSCILLATION_BREAK 但限幅太紧导致 Builder 无法修复 → improving_streak 不会增加 → 模式不退出 → 但 circuit breaker 会在 6 轮后停止
- 假设 improving_streak=2 但 Builder 需要大修改 → 1.5x 放宽（15 文件/300 行）→ 足够大部分场景

### P2-1: A/B 对比基线

**控制论原理**：决策前验证——在修改提交到系统前先验证效果。

**实现验证**：
- 在 `_compute_metrics` 之后、`_check_and_switch_mode` 之前检查 pass_rate 回归
- 阈值：`pass_rate < best - 0.15`（15% 显著回归）
- 触发时：立即回滚到 best_snapshot + 注入 `[A/B_ROLLBACK]` feedback

**自洽性检查**：
- ✅ 与 REGRESSION_RECOVERY 模式不冲突——A/B 是即时回滚（本轮），REGRESSION_RECOVERY 是模式切换（下一轮策略）
- ✅ 阈值 0.15 避免小波动触发误回滚——小回归由 REGRESSION_RECOVERY 的 streak >= 2 机制处理
- ✅ `ab_rollback_msg` 在 `current_feedback` 构建完成后注入，避免引用未初始化变量

**反事实推演**：
- 假设 best_snapshot 为 None（第 1 轮）→ `iteration > 1` 条件阻止触发 → 正确
- 假设 best_snapshot.files 为空 → `self._best_snapshot.get("files")` 为 falsy → 不触发 → 正确
- 假设回滚后 Builder 再次导致回归 → A/B 再次触发 → 但 circuit breaker 最终会停止

### P2-2: 可观测性仪表盘

**控制论原理**：可观测性（observability）——通过外部输出推断内部状态的能力。

**实现验证**：
- `_finalize_metrics_timeline()` 在所有 3 个出口点调用（converged、circuit_breaker、max_iterations）
- 导出为 `.runtime/state/metrics_{task_id}.json`，包含 13 个字段每轮
- `ConvergenceResult.metrics_timeline` 供程序化访问

**自洽性检查**：
- ✅ 包含 `sensor_disagreement` 字段——可观测 P1-1 仲裁结果
- ✅ 包含 `repair_mode`——可观测模式切换轨迹
- ✅ JSON 格式——可被任何工具消费（后续可扩展 HTML 仪表盘）

**反事实推演**：
- 假设 _metrics_history 为空 → timeline 为空列表 → JSON 文件写入 `[]` → 正确
- 假设 mode_history 比 metrics_history 短 → `mode_at = self._repair_mode`（fallback）→ 正确

## 三、交叉一致性校验

| 检查项 | 结果 |
|---|---|
| P0-1 changed_files 来源与 _prev_rollback_entries 一致 | ✅ |
| P0-2 context 数据来源与 _pass_rate_history/_mode_history 一致 | ✅ |
| P1-1 仲裁使用 missing_feature_count 与 _compute_metrics 计算一致 | ✅ |
| P1-2 adaptive limits 替换静态 cfg 值，拒绝消息同步更新 | ✅ |
| P2-1 回滚使用 _restore_project_files，与 REGRESSION_RECOVERY 一致 | ✅ |
| P2-2 在所有 3 个出口点调用，包含所有新字段 | ✅ |
| 新增 ConvergenceMetrics.sensor_disagreement 不破坏现有序列化 | ✅ (201 原有测试通过) |
| 新增 ConvergenceConfig.adaptive_limits/incremental_test_interval 有默认值 | ✅ |

## 四、回归风险评估

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| 增量测试漏报导致假收敛 | 中 | 每 3 轮全量校准 + circuit breaker |
| 前馈 context 过长消耗 token | 低 | 限制在 ~500 字符，5 条高信号量信息 |
| A/B 回滚阈值 0.15 不适合所有项目 | 低 | 可配置（硬编码但易于改为 config） |
| 自适应限幅过紧导致 Builder 无法修复 | 低 | circuit breaker 6 轮兜底 + adaptive_limits 开关 |
| metrics_timeline 文件写入失败 | 极低 | 在 finally 之外，但不影响主流程（仅日志） |

## 五、结论

6 项优化（P0-1, P0-2, P1-1, P1-2, P2-1, P2-2）全部实施完成，226 测试全绿，第一性原理推演和反事实推演验证通过。优化涉及 4 个文件修改 + 1 个新测试文件：

- `asr/controller/convergence.py` — P0-2/P1-1/P1-2/P2-1/P2-2 核心逻辑
- `asr/agents/tester.py` — P0-1 增量测试
- `asr/config/models.py` — 新增配置字段
- `asr/events/models.py` — ConvergenceMetrics 新增字段
- `tests/test_control_theory_v3.py` — 25 个新测试
