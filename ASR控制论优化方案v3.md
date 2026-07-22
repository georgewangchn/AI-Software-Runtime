# ASR 控制论优化方案 v3

> 基于控制论五要求（可观测、可控制、可稳定、反馈可靠、执行器可约束）系统性推演

## 一、现状审视：控制论映射

将 ASR 系统映射到经典闭环控制理论：

| 控制论概念 | ASR 对应组件 | 当前实现状态 |
|---|---|---|
| 被控对象 | 项目代码库 | ✅ 完整 |
| 地面真值传感器 | Tester (pytest) | ✅ 可靠，但每次跑全量测试 |
| 噪声传感器 | Analyzer (LLM 语义判断) | ✅ 已标记为噪声，不用于控制决策 |
| 控制器 | ConvergenceController | ✅ 含趋势判断、状态机、circuit breaker |
| 执行器 | Builder (opencode LLM) | ✅ 可约束（限幅+Guards），但缺少前馈 |
| 反馈回路 | test_pass_rate → trend → mode switch | ✅ 闭环完整 |
| 参考值 | Specification (DESIGN.md) | ✅ 有，但只通过 Analyzer 对齐 |
| 安全栅栏 | Formal Guards + patch 限幅 + hysteresis | ✅ 六轮推演已加固 |
| 状态机 | RepairMode (6态: INITIAL→TEST_FIX→SPEC_COMPLETION→OSCILLATION_BREAK→REGRESSION_RECOVERY→FINAL_VERIFICATION) | ✅ 含滞回防抖 |

**已解决的问题（前六轮+三轮自动化）：**
- 回滚机制（_best_snapshot + REGRESSION_RECOVERY）
- 振荡检测（pass_rate 纹波 + patch fingerprint + failure fingerprint）
- 滞回防抖（streak >= 2 才切模式）
- Formal Guards（测试删除检测 + 语法检查 + bypass 精确匹配）
- Circuit breaker（连续 N 轮无改善则停止）
- FINAL_VERIFICATION 模式（防止假收敛）

## 二、第一性原理推演：剩余的控制论缺陷

### 缺陷 1：反馈延迟过大（P0）

**控制论原理**：闭环控制系统中，反馈延迟 T_delay 直接影响系统稳定性。延迟越大，控制器越难在正确的时刻做出正确的决策——因为当控制器收到信号时，系统状态已经发生了变化。

**ASR 现状**：每一轮迭代 Tester 都跑**全量测试**（`pytest -v --tb=short {sandbox}`）。对于中等规模项目（50+ 测试文件），这会导致：
- 反馈延迟 = 测试执行时间（可能 60-300 秒）
- 控制器在等待测试结果期间无法做任何决策
- 如果 Builder 只改了 `src/auth.py`，跑全部测试是浪费

**反事实推演**：假设增量测试将反馈延迟从 120s 降到 10s：
- max_iterations=10 时，总时间从 ~20min 降到 ~3min
- 更多迭代机会 → 更细粒度的修复 → 更高收敛概率
- 但增量测试本身有误差：如果变更影响了未追踪的依赖，可能漏报

### 缺陷 2：执行器缺少前馈信号（P0）

**控制论原理**：前馈控制（feedforward）是在扰动到达被控对象之前就进行补偿。纯反馈系统（无前馈）只能在被控对象偏离目标后才纠正——这天生有滞后。

**ASR 现状**：Builder 收到的信息是：
1. 测试失败列表（反馈——已经发生了的问题）
2. Analyzer 反馈（噪声——LLM 的语义判断）
3. RepairMode 标签（控制信号——当前在哪个模式）

Builder **缺少**的关键前馈信息：
- 本轮变更的 diff 摘要（Builder 自己改了什么，它可能不记得——尤其 session reset 后）
- 历史模式信号（"前 3 轮你在 oscillating，尝试过 A→B→A 的修改模式"）
- 文件级变更影响范围（"你改了 `models.py`，但 `tests/test_models.py` 也需要更新"）

**反事实推演**：假设 Builder 在每次调用前收到结构化 context：
- session reset 后不会"失忆"重复之前的错误修改
- Builder 能主动避免已知的振荡模式
- 但 context 过长会消耗 token，需要在信息量和成本间平衡

### 缺陷 3：双传感器无交叉验证（P1）

**控制论原理**：多传感器融合中，当两个传感器读数不一致时，需要仲裁机制。否则控制器会被噪声误导。

**ASR 现状**：
- 传感器 A（test_pass_rate）：地面真值，可靠
- 传感器 B（Analyzer error_score）：噪声，已正确地不用于控制决策
- 但当 test_pass_rate=1.0（全通过）而 Analyzer 报告有 missing_feature 时，系统依赖 FINAL_VERIFICATION 模式来处理——这本质是"传感器不一致时多跑一轮"，但没有真正的仲裁逻辑

**反事实推演**：假设增加仲裁逻辑：
- test_pass=1.0 + Analyzer=MISSING → 可能是测试不完整（测试没覆盖缺失功能）
- test_pass=0.3 + Analyzer=ALL_CLEAR → 可能是测试有 bug 或 Analyzer 有盲区
- 仲裁结果可以指导下一轮策略：补测试 vs 补代码 vs 补规格

### 缺陷 4：限幅参数是静态的（P1）

**控制论原理**：执行器的约束边界应该根据系统状态自适应调整。在收敛初期需要大步长（快速接近目标），在接近收敛时需要小步长（精细调整，防止超调）。

**ASR 现状**：`max_files_per_patch=10`, `max_lines_per_patch=200` 是全局静态值。只有 `allow_large_patch_in_initial=True`（第 1 轮允许大 patch）做了粗粒度区分。

**反事实推演**：
- trend=improving + iteration=2 → 放宽限幅（Builder 在正确方向上，让它走快点）
- trend=oscillating + iteration=5 → 收紧限幅（强制小步修改，配合 OSCILLATION_BREAK）
- trend=regressing → 极限收紧（只允许 1-2 个文件修改，降低破坏面）

### 缺陷 5：缺少 A/B 对比验证（P2）

**控制论原理**：在关键控制决策后，应验证决策效果再提交。即"先试后用"。

**ASR 现状**：Builder 修改代码后直接写回项目目录，然后 Tester 跑测试。如果修改导致回归，需要等下一轮 REGRESSION_RECOVERY 才能回滚——这中间有一个完整迭代周期的延迟。

**反事实推演**：假设 Builder 的修改先写入 sandbox，Tester 在 sandbox 里跑测试，通过后再合并到项目目录：
- 回归在 sandbox 阶段就被拦截，不污染项目状态
- 但增加了复杂度和延迟（sandbox → test → merge 流程更长）
- 适合作为 P2 优化，在核心控制论机制稳定后实施

### 缺陷 6：可观测性不足（P2）

**控制论原理**：控制系统的可观测性（observability）是指通过外部输出推断内部状态的能力。良好的可观测性是调试和优化的前提。

**ASR 现状**：
- `_metrics_history` 存了 ConvergenceMetrics 列表，但只在内存中
- 日志通过 `ASRLogger` 输出，但没有结构化的时序数据导出
- Circuit breaker 触发时保存了 JSON 快照，但这只是终态，不是过程数据
- 无法事后分析"第 5 轮为什么 trend 从 improving 突然变成 oscillating"

## 三、优化方案（按优先级）

### P0-1: 增量测试

**目标**：将反馈延迟从 O(全量测试) 降到 O(变更子集测试)

**实现方案**：

1. 在 `TesterAgent` 中增加 `_compute_affected_tests()` 方法
2. 基于本轮 diff（已有 `_rollback_entries` 的 diff 计算）确定变更的源文件
3. 通过 import 依赖图推断受影响的测试文件
4. 只跑受影响的测试子集
5. 每 N 轮（可配置，默认 3）跑一次全量测试作为校准

```python
# TesterAgent 新增方法
def _compute_affected_tests(self, changed_files: list[str], sandbox: Path) -> list[str]:
    """基于变更文件推断应跑的测试文件"""
    affected = set()
    for changed in changed_files:
        # 直接对应：src/auth.py → tests/test_auth.py
        stem = Path(changed).stem
        direct_test = sandbox / "tests" / f"test_{stem}.py"
        if direct_test.exists():
            affected.add(str(direct_test))
        # import 依赖：扫描测试文件中 import 了 changed 模块的
        for test_file in (sandbox / "tests").rglob("test_*.py"):
            content = test_file.read_text()
            if stem in content or changed.replace("/", ".") in content:
                affected.add(str(test_file))
    return list(affected) if affected else []  # 空则跑全量
```

**控制论意义**：降低反馈延迟 T_delay → 提升系统可控性 → 更多迭代机会 → 更高收敛概率

**风险与缓解**：
- 风险：增量测试漏报（变更影响了未追踪的依赖）
- 缓解：每 3 轮强制全量测试校准 + circuit breaker 兜底

### P0-2: 执行器前馈控制

**目标**：Builder 调用前注入结构化 context，降低盲修概率

**实现方案**：

1. 在 `convergence.py` 的 `_repairing_phase` 中，构建 `builder_context` 字典
2. 包含：上一轮 diff 摘要、最近 3 轮的 trend 和 mode 轨迹、文件级变更影响范围
3. 将 context 序列化为 prompt 前缀注入 Builder

```python
# convergence.py _repairing_phase 中新增
def _build_builder_context(self, iteration: int) -> str:
    """构建前馈信号——让 Builder 在动手前就了解系统状态"""
    parts = []
    # 1. 历史 trend 轨迹
    if len(self._pass_rate_history) >= 2:
        trajectory = self._pass_rate_history[-5:]
        parts.append(f"[TRAJECTORY] pass_rate 近5轮: {trajectory}")
    # 2. 模式切换历史
    if hasattr(self, '_mode_history') and self._mode_history':
        recent_modes = [m for m, _ in self._mode_history[-3:]]
        parts.append(f"[MODE_HISTORY] {' → '.join(recent_modes)}")
    # 3. 重复失败指纹
    if len(self._failure_fingerprints) >= 2:
        current_fp = self._failure_fingerprints[-1]
        repeat_count = self._failure_fingerprints[:-1].count(current_fp)
        if repeat_count >= 2 and current_fp != "none":
            parts.append(f"[REPEATED_FAILURE] 相同测试失败已出现 {repeat_count+1} 次，需要换策略")
    # 4. 当前 best snapshot 信息
    if self._best_snapshot:
        parts.append(f"[BEST_STATE] 最佳状态: iter={self._best_snapshot['iteration']}, "
                     f"pass_rate={self._best_snapshot['test_pass_rate']:.2f}")
    return "\n".join(parts)
```

**控制论意义**：前馈控制 → 执行器在扰动发生前就做补偿 → 减少无效迭代

**风险与缓解**：
- 风险：context 过长消耗 token
- 缓解：限制 context 在 500 字符以内，只保留最高信号量的信息

### P1-1: 双传感器交叉验证

**目标**：test_pass_rate 与 Analyzer 信号不一致时触发仲裁

**实现方案**：

1. 在 `_compute_metrics` 中增加 `sensor_disagreement` 字段
2. 定义仲裁规则：
   - test_pass=1.0 + Analyzer=MISSING → `INCOMPLETE_TESTS`（测试不覆盖缺失功能）
   - test_pass<0.5 + Analyzer=ALL_CLEAR → `TEST_QUALITY_ISSUE`（测试本身有问题）
   - 正常情况 → `AGREED`
3. 仲裁结果影响下一轮策略

```python
# convergence.py _compute_metrics 中新增
def _compute_sensor_agreement(self, test_pass_rate: float, 
                               missing_features: list, analysis_aligned: bool) -> str:
    if test_pass_rate >= 1.0 and missing_features:
        return "INCOMPLETE_TESTS"  # 测试通过但功能缺失 → 需要补测试
    if test_pass_rate < 0.5 and analysis_aligned:
        return "TEST_QUALITY_ISSUE"  # 测试大面积失败但 Analyzer 认为 OK → 检查测试
    return "AGREED"
```

**控制论意义**：多传感器融合 → 降低单一传感器噪声对控制决策的影响

### P1-2: 自适应限幅

**目标**：patch 限幅参数根据 trend 动态调整

**实现方案**：

```python
# convergence.py _repairing_phase 中，替换静态限幅
def _get_adaptive_limits(self) -> tuple[int, int]:
    """根据系统状态动态调整 patch 限幅"""
    cfg = self._config.convergence
    base_files = cfg.max_files_per_patch
    base_lines = cfg.max_lines_per_patch
    
    if self._repair_mode == "OSCILLATION_BREAK":
        return max(2, base_files // 3), max(30, base_lines // 3)
    elif self._repair_mode == "REGRESSION_RECOVERY":
        return max(1, base_files // 4), max(15, base_lines // 4)
    elif self._improving_streak >= 2:
        return int(base_files * 1.5), int(base_lines * 1.5)
    elif self._stalled_streak >= 2:
        return max(3, base_files // 2), max(50, base_lines // 2)
    return base_files, base_lines
```

**控制论意义**：变步长控制 → 初期大步快收敛，后期小步防超调

### P2-1: A/B 对比基线（Sandbox-first 验证）

**目标**：Builder 修改先在 sandbox 验证，通过后再合并到项目目录

**实现方案**：

1. Builder 的修改写入 sandbox 而非项目目录
2. Tester 在 sandbox 中跑测试
3. 如果测试通过率 >= best_snapshot → 合并到项目目录
4. 如果测试通过率 < best_snapshot → 丢弃，回滚到 best_snapshot

**控制论意义**：决策前验证 → 防止回归污染系统状态

**注意**：这需要对 Builder/Tester 的 sandbox 机制做较大重构，建议在 P0/P1 优化验证后再实施

### P2-2: 可观测性仪表盘

**目标**：导出 metrics_history 为结构化时序数据

**实现方案**：

1. 在 `ConvergenceResult` 中增加 `metrics_timeline: list[dict]`
2. 每轮迭代结束时将 metrics 序列化到 timeline
3. 运行结束后写入 `.runtime/state/metrics_{task_id}.json`
4. 可选：增加 HTML 仪表盘生成功能

```python
# convergence.py run() 结束时
result.metrics_timeline = [
    {
        "iteration": m.iteration,
        "test_pass_rate": m.test_pass_rate,
        "trend": m.trend,
        "error_score": m.error_score,
        "repair_mode": self._mode_history[i][0] if i < len(self._mode_history) else "unknown",
        "oscillation_score": m.oscillation_score,
    }
    for i, m in enumerate(self._metrics_history)
]
```

## 四、实施路线图

| 阶段 | 优化项 | 预计工作量 | 依赖 |
|---|---|---|---|
| Phase 1 | P0-1 增量测试 | 中 | 无 |
| Phase 1 | P0-2 前馈控制 | 小 | 无 |
| Phase 2 | P1-1 双传感器交叉验证 | 小 | P0-2 |
| Phase 2 | P1-2 自适应限幅 | 小 | 无 |
| Phase 3 | P2-1 A/B 对比基线 | 大 | P0-1, P1-2 |
| Phase 3 | P2-2 可观测性仪表盘 | 中 | 无 |

## 五、反事实推演：不实施这些优化的后果

1. **不做 P0-1（增量测试）**：项目规模增长后，每轮测试时间线性增长，max_iterations=10 时总时间可能超过 30 分钟，实际可用迭代次数被反馈延迟吃掉
2. **不做 P0-2（前馈控制）**：Builder session reset 后"失忆"，重复之前的错误修改模式——这在长任务（max_iterations > 5）中已经观察到
3. **不做 P1-1（双传感器验证）**：test_pass=1.0 但功能缺失的假收敛依赖 FINAL_VERIFICATION 兜底，但 FINAL_VERIFICATION 本身依赖 Analyzer——如果 Analyzer 也漏报，假收敛就会逃逸
4. **不做 P1-2（自适应限幅）**：OSCILLATION_BREAK 模式虽然降低了 temperature，但限幅仍然是静态的——Builder 可能用一个小 patch 反复改同一个文件，形成微观振荡
5. **不做 P2-1（A/B 基线）**：回归必须等下一轮才能发现，在 max_iterations 较小时可能没有足够的迭代次数来恢复
6. **不做 P2-2（可观测性）**：调试收敛失败时只能靠日志文本推理，缺乏结构化数据支撑，难以定位"哪一轮的哪个决策导致了发散"
