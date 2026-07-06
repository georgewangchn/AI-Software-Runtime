# AI Software Runtime（ASR）
## 基于控制论的自治式 AI 软件工程收敛运行时

**工程实践报告**

---

| 项目信息 | |
|---------|--|
| 项目名称 | AI Software Runtime（ASR）—— 基于控制论的自治式 AI 软件工程收敛运行时 |
| 赛道方向 | AI + 研发（考察规范驱动开发、多模态情境智能及研发效率提升能力） |
| 报告版本 | v2.0 |
| 系统版本 | ASR v2.0（含控制论优化，同步至 2026-07-06） |

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-05-26 | 初版 |
| v1.1 | 2026-05-26 | 基于代码实际状态修正：Spec 弱化事实、OpenCode 委派机制、Tester 自动生成测试 |
| v1.2 | 2026-05-26 | 修正臆造模型为 glm-4.7-fp8；突出"设计文档驱动的超长超复杂系统开发"核心价值 |
| v1.3 | 2026-05-26 | 承认 harness 有工具调用能力，差异化在于 ASR 提供了 harness 缺少的"收敛大脑" |
| v1.4 | 2026-05-28 | 统一 Agent prompt 为流水线模型；Tester 每轮生成/更新测试用例；Analyzer 改为 plain text 输出 |
| v1.5 | 2026-05-29 | 集成 oh-my-openagent 多智能体编排，移除 CI 模式抑制；修复非 UTF-8 文件解码崩溃 |
| **v2.0** | **2026-07-06** | **控制论优化**：引入显式控制指标（ConvergenceMetrics）、RepairMode 状态机、Patch 限幅与 Formal Guards、振荡检测、Circuit Breaker、结构化 Analyzer、Failure Fingerprint、FINAL_VERIFICATION 模式、Bypass 检测升级为硬 Guard；经六轮第一性原理推演验证 |

---

## 目录

1. 问题定义与背景
2. 控制论视角：ASR 的底层本质
3. 技术方案架构设计
4. 控制论优化体系（v2.0 核心升级）
5. 核心功能实现说明
6. 各功能模块使用说明
7. 创新说明
8. 落地部署方案
9. 端到端验证

---

## 一、问题定义与背景

### 1.1 核心问题：AI 写代码容易，写对代码难

用 AI 写代码的人都遇到过一个困境——**AI 很快就能生成代码，但很难生成正确的代码**。具体表现为四种典型失败模式：

| 失败模式 | 通俗解释 | 后果 |
|---------|---------|------|
| **越改越偏** | AI 没有方向感，改一轮偏一点，多轮后完全跑偏 | 最终产物和原始需求南辕北辙 |
| **修 A 坏 B** | AI 只看局部，修复一处但破坏了另一处 | 修一个 Bug 制造三个 Bug |
| **能跑但不全** | AI 不知道"做完了"的标准是什么 | 功能遗漏，代码能跑但需求没覆盖 |
| **死循环修复** | AI 和测试错误互相纠缠，永远停不下来 | 烧完 Token 也没产出 |

**根本原因**：现有 AI Coding 工具（OpenCode、Claude Code、Cursor Agent 等）已经是 harness 形态——它们能调用工具、操作文件、跑命令、甚至执行测试。但问题在于：**harness 只提供了"手脚"，没有提供"大脑"**。具体来说，harness 缺少三个关键能力：

1. **不知道什么时候该停**：harness 可以无限循环，但没有收敛判定逻辑——测试通过了就停？代码对齐了就停？没有定义
2. **不知道修坏了要回滚**：harness 只管往前冲，改坏了就继续改，没有"比上一轮更差就撤回"的退化防护
3. **不知道做完了的标准**：harness 跑测试、看报错，但不知道"代码是否完整覆盖了设计文档的所有要求"

软件工程的本质是**持续减少"实现"与"需求"之间的差距**，收敛和验证才是工程价值所在——harness 解决了"AI 能动手"，但没有解决"AI 能做完"。

### 1.2 核心洞察：约束大于智能

> **一个弱模型 + 强约束系统 > 一个强模型 + 无约束系统**

这就像自动驾驶：再好的司机没有红绿灯也会出事故，再差的新手在完备信号系统下也能安全到达。ASR 做的就是给 AI Coding 装"红绿灯"。

> 注意：这不是说 ASR 用便宜模型省钱——多轮迭代收敛会消耗大量 Token。这句话的真正含义是：**约束机制让 AI 的产出变得可控、可验证、可收敛**，而不是让 AI "裸奔"后靠人收拾残局。

### 1.3 技术背景与业务价值

```
现有 harness（OpenCode 等）：
  人工 → Opencode → 人工review → Opencode → 人工review → Opencode → ...（靠人驱动）

ASR（harness 之上的收敛运行时）：
  人工 → Design → Builder 生成 → Tester 测试 → 退化？→ 回滚
                                 ↓ 通过
                            Analyzer 对比设计文档 → 有偏差？→ 定向修复
                                 ↓ 对齐
                            收敛退出 ✅
```

**核心价值**：

> **ASR 解决的是"从设计文档到完整系统的自动化开发"问题——这是现有 AI Coding 工具普遍无法解决的难题。**

---

## 二、控制论视角：ASR 的底层本质

### 2.1 ASR 天然是控制论系统

软件开发的本质不是"写代码"，而是不断减少"需求"和"实现"之间的差异：

```
软件开发 = 需求与实现之间的持续差异消除
```

这和控制论中的闭环反馈机制高度一致：

```
目标 → 控制器 → 执行器 → 被控对象 → 传感器 → 反馈 → 控制器
```

在 ASR 中，对应关系如下：

| 控制论概念 | ASR 中的对应物 |
|---|---|
| 目标值 / Reference | `DESIGN.md`、结构化 Spec、验收标准 |
| 控制器 / Controller | `ASRController`（收敛状态机） |
| 执行器 / Actuator | `BuilderAgent`（LLM 驱动，不可控） |
| 被控对象 / Plant | 正在生成或修复的软件工程代码 |
| 传感器1 / Ground Truth Sensor | `TesterAgent`（pytest，确定性反馈） |
| 传感器2 / Noisy Sensor | `AnalyzerAgent`（LLM 驱动，含判断噪声） |
| 反馈 / Feedback | test_pass_rate、规格偏差、Analyzer findings |
| 状态记忆 / Memory | `EventStore`、`.runtime/events`、patch history |
| 控制动作 / Control Action | 生成 patch、回滚、切换 RepairMode、终止 |
| 收敛目标 / Convergence Goal | 测试全部通过，并且实现与规格一致 |

### 2.2 LLM 执行器的根本约束

ASR 用 LLM 作为执行器，但 LLM 不是可靠的确定性执行器。它的根本约束：

- **不可控**：prompt 是软约束，LLM 可以忽略任何指令
- **输出随机**：相同输入产生不同输出
- **反馈延迟极高**：每轮迭代需要 30-60 秒
- **上下文遗忘**：跨会话丢失修改历史

因此，ASR 的核心价值在于：

> **不相信单次生成，而相信闭环收敛。**

```
弱模型 + 强约束 + 外部反馈 + 持续修复 = 稳定软件生成系统
```

### 2.3 从 Agent Workflow 到 Cybernetic Software Runtime

v2.0 的核心升级方向是：**把隐式反馈变成显式误差信号，把经验规则变成可观测、可调参、可分析的控制策略。**

| 维度 | v1.x（工程闭环） | v2.0（显式控制系统） |
|------|----------------|-------------------|
| 误差信号 | 测试失败数、Analyzer findings | ConvergenceMetrics（15+ 字段统一指标） |
| 收敛判断 | "测试通过 + 语义对齐" | test_pass_rate 趋势 + circuit breaker |
| 回滚机制 | inline rollback（1.5x 阈值） | REGRESSION_RECOVERY + _best_snapshot |
| 振荡检测 | 无 | patch fingerprint + failure fingerprint + oscillation_score |
| 执行器约束 | prompt 级指令 | RepairMode 状态机 + Patch 限幅 + Formal Guards |
| 模式切换 | 无 | hysteresis 自动切换（6 种 RepairMode） |

---

## 三、技术方案架构设计

### 3.1 总体架构

ASR 是一个三层架构的自治运行时，核心思路是**把 AI 当执行器，把人类当裁判**：

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户层                                    │
│   CLI 命令行（run / run-dag / init / compare）                    │
│   输入：DESIGN.md                                                 │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│                     控制层（ASR Runtime）                         │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              ASRController（收敛状态机）                   │    │
│  │                                                           │    │
│  │   ┌─── ConvergenceMetrics（显式控制指标）───┐              │    │
│  │   │ test_pass_rate / trend / oscillation    │              │    │
│  │   │ error_score / repeated_failure_count     │              │    │
│  │   └──────────────────────────────────────────┘              │    │
│  │                                                           │    │
│  │   REPAIRING ──→ TESTING ──→ ANALYZING                    │    │
│  │       ↑            │           │                          │    │
│  │       │            ↓           ↓                          │    │
│  │  RepairMode    退化检测      语义裁决                       │    │
│  │  auto-switch   _best_snapshot 对齐?→CONVERGED             │    │
│  │       ↑            │                         │            │    │
│  │       └────────────┴─── 修复指令 ←────────────┘            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─── A2A 协作流程（三 Agent 独立进程、独立会话）──────────────┐    │
│  │  ┌─────────────┐  A2A   ┌─────────────┐  A2A  ┌───────┐│    │
│  │  │BuilderAgent │──────→│ TesterAgent │─────→│Analzr ││    │
│  │  │ 生成/修复    │ 事件  │ 测试生成+执行│ 事件 │语义裁决││    │
│  │  │ 带会话记忆   │      │ Sandbox隔离 │      │Sbx隔离││    │
│  │  └─────────────┘      └─────────────┘      └───────┘│    │
│  └──────────────────────────────────────────────────────────┘    │
          │                │                │
┌─────────▼────────────────▼────────────────▼─────────────────────┐
│                 执行层（oh-my-openagent + OpenCode）               │
│  oh-my-openagent 多智能体编排：IntentGate→Prometheus(规划)→       │
│  Metis(缺口分析)→Momus(审查)→Atlas(分发)→Sisyphus(执行)          │
│  opencode run --format json --dir <project> [--session ID]        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     基础设施层                                    │
│  EventStore（事件审计）│ PatchEngine（diff修复）│ Logger+Tracker  │
│  全文件化存储 · FileLock原子写 · 可回放                           │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 核心模块职责

| 模块 | 文件 | 做什么 | 一句话 |
|------|------|--------|--------|
| **ASRController** | `controller/convergence.py` | 收敛状态机、控制论指标计算、RepairMode 自动切换、退化回滚、终止评估 | 大脑：决定什么时候修、什么时候停 |
| **BuilderAgent** | `agents/builder.py` | 功能开发，含基本单元测试；带 OpenCode 会话延续 | 开发专家：写代码实现功能 |
| **TesterAgent** | `agents/tester.py` | 每轮自动生成/更新测试用例 + pytest 执行；Sandbox 隔离 | 测试专家：写专业测试跑测试 |
| **AnalyzerAgent** | `agents/analyzer.py` | 对比设计文档与代码，diff-only 模式，输出结构化偏差分析 | 验收专家：查代码是否符合设计 |
| **OpenCode Backend** | `agents/opencode_backend.py` | 子进程调用 OpenCode CLI，解析 JSON 流 | 手：连接 AI 大脑和文件系统 |
| **EventStore** | `events/store.py` | 文件化事件存储、A2A 通信、补丁持久化 | 黑匣子：记录一切，可回放 |
| **DAGExecutor** | `dag/executor.py` | 大任务拆解、并行执行收敛循环 | 并行调度器 |
| **Config System** | `config/models.py` | Pydantic v2 配置模型，含控制论参数 | 配置中心 |

### 3.3 ASR 与 OpenCode 的职责分工

| 层 | 负责什么 | 不负责什么 |
|----|---------|----------|
| **ASR（约束层）** | 收敛循环、退化检测、语义裁决、会话管理、事件审计、控制论指标 | 不直接调用 LLM、不直接改文件 |
| **OpenCode（执行层）** | LLM 调用、代码生成/修改、Tool Calling、Context 管理 | 不知道收敛、不知道回滚、不知道裁决 |

### 3.4 系统运行阶段（Roadmap）

| 阶段 | 状态 | 核心能力 |
|------|------|---------|
| Phase 1: 单任务收敛 MVP | ✅ 已实现 | Builder+Tester+Analyzer 收敛循环 |
| Phase 2: 文件化 A2A 事件系统 | ✅ 已实现 | 19 种事件类型 + Inbox 轮询 + 事件回放 |
| Phase 3: Task DAG 并行 | ✅ 已实现 | 任务拆解 + 拓扑排序 + asyncio 并行 |
| Phase 4: 显式控制指标 | ✅ 已实现 | ConvergenceMetrics、error_score、trend、test_pass_rate |
| Phase 5: 稳定性控制 | ✅ 已实现 | patch/failure fingerprint、振荡检测、RepairMode hysteresis auto-switch |
| Phase 6: 控制 Builder 输出强度 | ✅ 已实现 | patch 限幅、hard reject、Formal Guards（test删除+语法检查+bypass检测） |
| Phase 7: 结构化 Analyzer | ✅ 已实现 | StructuredFinding、severity/confidence/blocking、diff-only 模式 |
| Phase 8: Verification Mesh | 🔮 规划中 | SecurityAgent + PerformanceAgent + ArchitectureAgent |

---

## 四、控制论优化体系（v2.0 核心升级）

v2.0 经历六轮第一性原理推演，逐步构建了完整的控制论优化体系。以下按控制论五要求组织：

### 4.1 反馈信号可靠性

#### 4.1.1 双传感器架构

ASR 有两个反馈源，信号可靠性不同：

| 传感器 | 信号类型 | 可靠性 | 控制用途 |
|--------|---------|--------|---------|
| **TesterAgent** | test_pass_rate（pytest 客观结果） | **确定性**（ground truth） | 主控制信号：趋势判断、circuit breaker、模式切换 |
| **AnalyzerAgent** | error_score（LLM 判断） | **含噪声** | 仅 logging，不参与控制决策 |

> **控制论原则**：不使用含噪声的传感器做反馈控制。error_score 虽然计算了，但标记为 `[Analyzer噪声]`，仅用于日志和人类可观测性，不驱动任何控制决策。

#### 4.1.2 ConvergenceMetrics（显式控制指标）

每轮迭代后生成统一指标，包含 15+ 字段：

```python
ConvergenceMetrics:
    iteration: int
    test_failed_count: int          # 硬约束
    test_error_count: int           # 编译错误
    test_pass_rate: float           # 地面真值（PRIMARY 信号）
    missing_feature_count: int      # 语义信号（噪声）
    logic_issue_count: int          # 语义信号（噪声）
    constraint_violation_count: int
    high_severity_count: int
    patch_count: int
    changed_file_count: int
    changed_line_count: int
    rollback_count: int
    repeated_failure_count: int     # N1: 相同失败反复出现
    oscillation_score: float        # 振荡程度
    error_score: float              # 综合误差（含噪声，仅 logging）
    trend: str                      # improving/regressing/stalled/oscillating
```

#### 4.1.3 test_pass_rate 计算修复

pass_rate 计算使用 `max()` 而非累加，避免多事件场景下 pass_rate > 1.0：

```python
# FIX: use max() for both total and passed to avoid double-counting
total_tests = max(total_tests, evt.payload.get("total", 0))
passed_tests = max(passed_tests, evt.payload.get("passed", 0))
test_pass_rate = passed_tests / total_tests if total_tests > 0 else 0.0
```

### 4.2 执行器可约束性

LLM 执行器不可控（prompt 是软约束），ASR 通过三层硬约束将其变为"受控执行器"：

#### 4.2.1 RepairMode 状态机

六种修复模式，每种实质改变 Controller 对 Builder 的调用方式：

```
INITIAL_GENERATION
  ↓ (iteration 1 → 2)
TEST_FIX ←─────────────────────────────────────┐
  ↓ (stalled_streak >= 2, missing_features > 0)  │
SPEC_COMPLETION                                  │
  ↓ (oscillation_score >= 0.7)                   │
OSCILLATION_BREAK ──(improving >= 2)────────────┘
  ↓ (regressing_streak >= 2)
REGRESSION_RECOVERY ──(improving >= 1)──→ TEST_FIX
  ↓ (tests pass, no analyzer)
FINAL_VERIFICATION ──(Analyzer finds issues)──→ SPEC_COMPLETION / TEST_FIX
                   ──(Analyzer: ALL CLEAR)──→ 收敛
```

每种模式的**硬约束**：

| RepairMode | 硬约束（不依赖 prompt） | 软约束（prompt 级） |
|---|---|---|
| COMPILE_FIX | 只传编译错误（过滤 test failures） | "只修复编译错误" |
| SPEC_COMPLETION | — | "只新增缺失的文件/功能" |
| OSCILLATION_BREAK | temperature_override = 0.1 | "每次最多3个文件" |
| REGRESSION_RECOVERY | _best_snapshot 文件回滚 | — |
| FINAL_VERIFICATION | force_analyze = True | "不做代码修改" |

#### 4.2.2 Patch 限幅（Hard Reject）

每轮修复的"控制增益"有硬限制：

```python
# 超过限幅直接拒绝并回滚，不进入测试阶段
if (summary.get("files", 0) > cfg.max_files_per_patch
        or (summary.get("added", 0) + summary.get("removed", 0)) > cfg.max_lines_per_patch):
    # [PATCH_REJECTED] — 回滚所有文件，通知 Builder 缩小范围
    return events  # exit early
```

初始生成（iteration=1）豁免限幅，允许大范围创建文件。

#### 4.2.3 Formal Guards（硬约束三件套）

在 patch 应用后、测试前，三道静态检查关卡：

| Guard | 检测内容 | 触发动作 |
|-------|---------|---------|
| **Guard 1: 测试删除检测** | Builder 删除了 test_*.py 或 tests/ 下的文件 | 拒绝 patch + 回滚 |
| **Guard 2: 语法检查** | 对所有 .py 文件（含新建文件）执行 `ast.parse()` | 拒绝 patch + 回滚 |
| **Guard 3: Bypass 检测** | diff 新增行中检测 `except:`、`return expected`、`@pytest.mark.skip`、生产代码中 `from unittest.mock import` | 拒绝 patch + 回滚 |

> Guard 3 使用精确行级匹配而非子串匹配，避免 `class Foo: pass` 等合法代码被误报。

### 4.3 系统稳定性

#### 4.3.1 振荡检测（三重指纹）

```python
# 1. test_pass_rate 振荡（主信号）
if deltas[-1] * deltas[-2] < 0:  # 增量正负交替
    oscillation_score = 0.7

# 2. patch fingerprint 振荡（A-B-A-B 模式）
if len(set(recent_fp)) <= 2 and recent_fp[0] == recent_fp[2]:
    oscillation_score = max(oscillation_score, 0.9)

# 3. failure fingerprint（相同测试反复失败 3+ 次）
if repeated_failure_count >= 3:
    oscillation_score = max(oscillation_score, 0.85)
```

`oscillation_score >= 0.7` 自动切换到 OSCILLATION_BREAK 模式。

#### 4.3.2 Circuit Breaker

```python
# pass_rate 没有上升就计数（只有持平或下降才触发）
if self._pass_rate_history[-1] <= self._pass_rate_history[-2]:
    self._no_improvement_streak += 1
else:
    self._no_improvement_streak = 0

# 连续 N 轮无改善 → 停止并保存状态供人工审查
if self._no_improvement_streak >= circuit_threshold:
    self._emit_stuck(...)  # 保存 .runtime/state/stuck_*.json
```

> **关键修复**：早期版本使用 `pass_rate[-1] <= pass_rate[-2] + 0.05`，把"改善 4%"误判为"无改善"，导致系统在稳步收敛时被误杀。修复后只有 pass_rate 真正持平或下降才触发。

#### 4.3.3 退化回滚（_best_snapshot 机制）

```python
# test_pass_rate 创新高时，快照项目文件真实状态
if test_pass_rate > self._best_snapshot["test_pass_rate"] + 0.01:
    self._best_snapshot = {
        "iteration": iteration,
        "test_pass_rate": test_pass_rate,
        "files": self._snapshot_project_files(),  # post-Builder 真实状态
    }

# REGRESSION_RECOVERY 时恢复到最佳状态
if self._regressing_streak >= 2:
    self._restore_project_files(self._best_snapshot["files"])
```

> **关键修复**：早期版本保存的 `_rollback_entries` 在 `_compute_metrics` 调用前已被 `clear()`，导致回滚机制完全失效（保存的是空列表）。修复后直接快照项目文件的真实内容。

#### 4.3.4 Hysteresis（滞回防抖动）

模式切换需要连续 2 轮同趋势才触发，防止单轮波动导致频繁切换：

```python
# stalled_streak >= 2 才切换到 SPEC_COMPLETION
# regressing_streak >= 2 才切换到 REGRESSION_RECOVERY
# improving_streak >= 2 才从 OSCILLATION_BREAK 退出
# improving_streak >= 1 才从 REGRESSION_RECOVERY 退出（回滚已执行一次）
```

#### 4.3.5 模式退出条件（防死循环）

每个模式都有明确的退出条件，不存在死循环路径：

| 模式 | 退出条件 | 目标模式 |
|------|---------|---------|
| OSCILLATION_BREAK | improving_streak >= 2 | TEST_FIX |
| REGRESSION_RECOVERY | improving_streak >= 1 | TEST_FIX |
| FINAL_VERIFICATION + Analyzer 发现问题 | force_analyze + not spec_aligned | SPEC_COMPLETION / TEST_FIX |
| FINAL_VERIFICATION + Analyzer ALL CLEAR | convergence_streak >= 3 | CONVERGED |

### 4.4 可观测性

#### 4.4.1 每轮指标事件

每轮迭代后发出 `ConvergenceMetricsEvent`，写入 `.runtime/events/`，可任意回放：

```json
{
  "metrics": {
    "iteration": 3,
    "test_pass_rate": 0.80,
    "trend": "improving",
    "oscillation_score": 0.0,
    "repeated_failure_count": 0,
    "error_score": 2.5
  },
  "previous_error_score": 4.0
}
```

#### 4.4.2 反馈降噪

反馈窗口从 30 条减为 15 条，模式切换时清空旧反馈（只保留 `[PRIORITY]` 和 `[COMPILE_ERROR]` 项），避免 Builder 看到矛盾、过时的历史反馈。

### 4.5 可控制性

#### 4.5.1 FINAL_VERIFICATION 模式

防止"测试通过但需求未完整实现"的假收敛：

1. 测试通过但 Analyzer 未运行 → 切换到 FINAL_VERIFICATION
2. FINAL_VERIFICATION 强制 force_analyze = True
3. Builder 被要求不做代码修改，只重新确认 DESIGN.md 完整性
4. Analyzer 运行后：
   - ALL CLEAR → 收敛
   - 发现问题 → 退出到 SPEC_COMPLETION 或 TEST_FIX

#### 4.5.2 Failure Fingerprint

对测试失败的 nodeid 集合做 SHA-256，相同测试反复失败产生相同指纹。`repeated_failure_count >= 3` 时提升 oscillation_score 到 0.85，触发 OSCILLATION_BREAK。

---

## 五、核心功能实现说明

### 5.1 收敛循环：ASR 的心脏

```
每轮迭代：

  ① REPAIRING（修复阶段）
     首轮：Builder 读 DESIGN.md，从零生成代码
     后续：根据测试失败 + 语义分析反馈 + RepairMode 指令，定向修复
     → 修复前，Controller 自动快照所有文件（rollback 备份）
     → 修复后，执行 Patch 限幅 + Formal Guards 硬约束检查

  ② TESTING（测试阶段）
     复制项目到 Sandbox → OpenCode 生成 pytest 测试 → 执行 pytest
     → 测试文件持久化回写 tests/（下次直接复用）

  ③ ANALYZING（语义裁决）
     diff-only 模式：只看本轮变更而非全量代码
     对比 DESIGN.md 与代码实现
     → 测试通过 + 分析对齐 → convergence_streak++
     → 连续 3 轮对齐 → CONVERGED（收敛成功！）

  ④ 控制论决策（每轮执行）
     _compute_metrics → 计算 test_pass_rate、trend、oscillation_score
     circuit breaker → 连续 N 轮无改善则停止
     _check_and_switch_mode → hysteresis 自动切换 RepairMode
     _best_snapshot → pass_rate 创新高时保存快照
```

### 5.2 双层裁决——AI 不能自己判自己及格

| 裁判 | 判什么 | 怎么判 | 通俗类比 |
|------|--------|--------|---------|
| **Tester（硬约束裁判）** | 代码能不能跑对 | 在隔离 Sandbox 里生成测试、跑 pytest | 理科考试：答案对就是对，错就是错 |
| **Analyzer（语义裁判）** | 代码是不是符合设计 | 对比 DESIGN.md 与代码，找遗漏和偏差 | 文科考试：有没有遗漏论点、偏不偏题 |

```
判定流程：
  Tester 说不通过 → 打回 Builder 重修
  Tester 说通过 → 再交 Analyzer 审
  Analyzer 说还有偏差 → 携带 findings 进入下一轮修复
  Analyzer 说对齐了 → convergence_streak++ → 连续3轮 → 收敛成功！
```

### 5.3 退化回滚——_best_snapshot 机制

当系统持续退化（regressing_streak >= 2）时，回滚到 pass_rate 最高的历史状态：

```python
# REGRESSION_RECOVERY 模式：只在 regressing_streak >= 2 时回滚
if self._regressing_streak >= 2:
    source_files = self._best_snapshot.get("files")  # 真实项目文件状态
    self._restore_project_files(source_files)        # 恢复 + 清理新增文件

# improving_streak >= 1 时退出 REGRESSION_RECOVERY
# 不再每轮回滚，避免 回滚→改进→回滚→改进 的无限振荡
```

### 5.4 Bypass 检测——AI 想作弊？系统看得见

Guard 3 使用精确行级匹配检测 bypass 模式：

```python
# 精确模式（非子串匹配）：
if stripped.startswith("except:"):          # 裸异常捕获
    guard_violations.append("[GUARD:BYPASS] bare except:")
if "return expected" in stripped.lower():   # 硬编码返回值
    guard_violations.append("[GUARD:BYPASS] hardcoded return")
if "@pytest.mark.skip" in stripped:         # 跳过测试
    guard_violations.append("[GUARD:BYPASS] test skipped")
# mock 检测：追溯 diff 文件名，只在生产代码中触发
if "from unittest.mock import" in stripped:
    if "test_" not in current_file:         # 正确检查文件名而非项目目录
        guard_violations.append("[GUARD:BYPASS] mock in production code")
```

### 5.5 OpenCode 委派执行机制

ASR 的所有 Agent 通过 **oh-my-openagent** 的多智能体编排增强调用 OpenCode CLI 子进程：

| 阶段 | 组件 | 职责 |
|------|------|------|
| **意图分类** | IntentGate | 识别任务类型，路由到最合适的 Agent |
| **规划** | Prometheus + Metis | 访谈式规划 + 缺口分析 |
| **审查** | Momus | 执行前审查 |
| **分发执行** | Atlas → Sisyphus | TODO 列表分发，持续工作直到 100% 完成 |
| **编辑保证** | Hash-anchored edits | 每次编辑前校验内容哈希 |

### 5.6 Sandbox 隔离机制

Tester 和 Analyzer 都在 `.asr_sandbox/` 中隔离执行，防止 OpenCode 修改影响项目代码。

### 5.7 设计文档驱动的开发模式

ASR 实际的输入是 **DESIGN.md**（必需）。三个 Agent 共享统一的流水线身份认知：

```
开发专家开发代码 → 测试专家编写测试用例 → 验收专家验收结果 → 反馈给开发专家
```

### 5.8 本地化 A2A 事件系统

ASR 不采用 Kafka / NATS / 微服务 / 分布式总线。所有 Agent 通信统一通过**文件化 A2A 协议**。

#### 5.8.1 事件类型

20 种事件类型覆盖完整生命周期：

```
TaskCreated, CodeGenerated, TestStarted, TestFailed, TestPassed, TestError,
SpecDiffFound, SpecAligned, PatchRequested, PatchGenerated, PatchApplied,
PatchFailed, PatchRolledBack, AnalyzeRequested, AnalyzerFeedback,
ConvergenceIteration, Converged, Stuck, ErrorOccurred, MeshVerdict
```

#### 5.8.2 事件文件格式

```json
{
  "event_id": "uuid",
  "task_id": "task_001",
  "type": "TEST_FAILED",
  "from": "tester",
  "to": "controller",
  "payload": {
    "total": 15, "passed": 12, "failed": 3,
    "failures": [{"nodeid": "test_xxx", "message": "AssertionError"}]
  }
}
```

- **原子写入**：FileLock + tmp→rename 模式
- **事件回放**：所有事件存储在 `.runtime/events/`，可任意回放重建状态

#### 5.8.3 两种 A2A 通信模式

**1. 直接调用模式（默认）**：Controller 直接调用 `agent.process(event)`，Agent 返回结果事件列表。Controller 将结果写入 EventStore 和 Inbox（供审计与回放）。

**2. 解耦模式（--decoupled）**：AgentRunner 独立异步轮询 inbox/ 目录（asyncio poll loop，默认 0.1s 间隔），AgentOrchestrator 管理所有 Runner 生命周期。两种模式产生相同的事件流，可在运行时切换。

> **核心原则**：Agent 的**认知职责**分离（Builder ≠ Tester ≠ Analyzer），而非通信介质分离。

### 5.9 Task DAG 并行执行

#### 5.9.1 核心模型

**TaskNode**：
- `id`, `name`, `description`：标识与描述
- `files`：关联的源文件列表
- `depends_on`：依赖的前置节点 ID 列表
- `status`：PENDING / RUNNING / CONVERGED / STUCK / SKIPPED
- `iterations`, `patch_count`, `errors_resolved`：执行统计

**TaskDAG**：
- 节点管理：`add_node()`, `get_ready_nodes()`, `mark_completed()`
- 拓扑排序：`topological_order()`（DFS 实现）
- 环检测与冲突解决：`_resolve_file_conflicts()`（共享文件的节点建立隐式依赖）
- 完成判定：`all_done()`

#### 5.9.2 TaskDecomposer（任务拆解）

两种拆解策略：
1. **基于 Spec.features 拆解（特征驱动）**：每个 feature 生成一个 TaskNode，通过文件名匹配推断 files 关联
2. **基于测试失败拆解（修复驱动）**：按失败文件的模块分组，每个分组生成一个修复节点

#### 5.9.3 DAGExecutor（并行执行）

```python
while not dag.all_done():
    ready = dag.get_ready_nodes()        # 获取依赖已满足的节点
    await asyncio.gather(                 # 并行执行
        *(self._run_node(dag, n, spec) for n in ready)
    )
```

每个节点执行：构建节点专用 Specification → 创建独立 ASRController → 运行完整收敛循环 → 记录结果。

### 5.10 OpenCode 后端委派机制

所有 ASR Agent 通过 subprocess 调用 OpenCode CLI 完成实际工作：

| 函数 | 用途 | 调用方式 |
|------|------|---------|
| `opencode_completion(prompt, project_dir)` | TesterAgent/AnalyzerAgent 使用 | `opencode run --model <model> --format json --dir <dir>` |
| `opencode_diff(prompt, project_dir, session_id)` | BuilderAgent 使用 | 支持 `--continue` 模式（session 延续），通过 `git diff --cached HEAD` 提取 unified diff |

**BuilderAgent 的 Session 延续**：首次调用创建新 session，后续调用传入 session_id + `--continue` → 在同一 session 中继续，Builder 能"记住"之前的修改历史。

### 5.11 Sandbox 隔离执行

Tester 和 Analyzer 在 `.asr_sandbox/` 中隔离执行：

**TesterAgent 执行流程**：
1. 清理 `.asr_sandbox/tester/`
2. 复制项目文件到 sandbox（排除 .asr_sandbox, .git, .runtime, .pytest_cache）
3. OpenCode 在 sandbox 中生成 pytest 测试文件
4. 运行 `pytest -v --tb=short`（600s 超时）
5. 解析 pytest 输出为结构化结果
6. 将生成的测试文件从 sandbox 回写项目 `tests/`
7. 清理 sandbox

**AnalyzerAgent 执行流程**：
1. 清理 `.asr_sandbox/analyzer/`
2. 复制项目文件到 sandbox
3. OpenCode 在 sandbox 中分析，输出分析报告
4. 解析结果为结构化偏差分析
5. 清理 sandbox

---

## 六、各功能模块使用说明

### 6.1 环境准备

**系统要求**：
- Python 3.12.9（通过 pyenv 管理）
- OpenCode CLI >= 1.15
- oh-my-openagent >= 3.17（推荐）

```bash
cd /path/to/asr
pyenv local 3.12.9
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**配置 LLM 后端**：

```bash
# OpenCode 配置 ~/.config/opencode/opencode.json
# ASR 环境变量：
ASR_OPENCODE_TIMEOUT=14400
ASR_VERBOSE=1
```

### 6.2 项目初始化

```bash
python -m asr.cli.main init --project ./my_project
```

**项目必需文件**：
```
my_project/
├── DESIGN.md              # 设计文档（必需！）
└── tests/                 # 测试文件（可空，TesterAgent 自动生成）
```

### 6.3 执行收敛

```bash
python -m asr.cli.main run \
  --project /path/to/project \
  --max-iterations 10
```

**实时进度输出**：
```
ASR 收敛运行时 [直接模式]
项目路径: /path/to/project
最大迭代轮次: 10

  [第1轮] 代码生成  错误:0  🔧  | 补丁:0 文件:3 代码行:156 初始生成
  [第2轮] 测试验证  错误:3  ❌  | 通过:12/15 失败:test_foo,test_bar
  [第3轮] 代码修复  错误:3  🔧  | 修复3个失败
  [第4轮] 测试验证  错误:0  ✅  | 通过:15/15
  [第5轮] 规格分析  错误:0  ✅  | 规格:一致

✅ 已收敛 — 所有测试通过且规格一致
迭代轮次: 5 | 事件数: 23
```

### 6.4 日志与可观测性

| 日志文件 | 位置 | 内容 |
|---------|------|------|
| 收敛日志 | `.runtime/logs/asr.log` | 每轮迭代的阶段、错误数、RepairMode 切换、控制论指标 |
| LLM 追踪 | `.runtime/logs/llm.jsonl` | 每个 Agent 的 Token 消耗明细 |
| 事件审计 | `.runtime/events/*.json` | 完整事件流，含 ConvergenceMetricsEvent |
| 运行状态 | `.runtime/state/*.json` | 收敛/卡住终态（circuit breaker 触发时保存） |

---

## 七、创新说明

### 7.1 核心价值：从设计文档到完整系统的自动化开发

| 能力层级 | 典型工具 | 能做什么 | 做不到什么 |
|---------|---------|---------|----------|
| **L1 代码补全** | GitHub Copilot | 写函数、补逻辑 | 不知道整个系统该长什么样 |
| **L2 单任务对话** | ChatGPT、Claude | 聊天式改一个文件 | 多文件联动、跑测试验证 |
| **L3 Agent 模式** | Cursor Agent、Claude Code | 自动探索项目、改多个文件 | 没有收敛机制、没有退化防护 |
| **L4 设计驱动开发** | **ASR（本方案）** | 读设计文档→生成多模块系统→自动测试→语义验证→收敛 | — |

### 7.2 五大核心创新

#### 创新一：A2A 多智能体协作——让 AI 团队开发成为可能

三个独立 Agent，通过文件化 A2A 事件协议协作。Builder 有状态延续（session_id），Tester/Analyzer 无状态隔离。支持 `--decoupled` 解耦模式。

#### 创新二：双层裁决——AI 不能自己给自己打分

Tester（硬裁判，pytest 客观结果）+ Analyzer（软裁判，语义对比设计文档），两个独立裁判都通过才算及格。

#### 创新三：退化自动回滚——改坏了自动撤回

_best_snapshot 机制：test_pass_rate 创新高时保存项目文件快照，REGRESSION_RECOVERY 时恢复到最佳状态。

#### 创新四：Bypass 检测——AI 作弊自动发现

Guard 3 精确行级匹配检测 `except:`、`return expected`、`@pytest.mark.skip`、生产代码中的 `mock`，检测到直接拒绝 patch 并回滚。

#### 创新五：控制论收敛状态机——从 Agent Workflow 到 Cybernetic Runtime

六种 RepairMode + hysteresis 自动切换 + circuit breaker + 振荡检测，让不可控的 LLM 执行器在闭环控制下稳定收敛。

### 7.3 与现有方案的系统对比

| 对比维度 | GitHub Copilot | Claude Code | Cursor Agent | **ASR** |
|---------|---------------|-------------|-------------|---------|
| **多智能体协作** | 单 Agent | 单 Agent | 单 Agent | **A2A 三 Agent 协作** |
| **验证方式** | 无 | LLM 自评 | LLM 自评 | **双层外部验证** |
| **收敛机制** | 无 | 无 | 无 | **ConvergenceMetrics + circuit breaker** |
| **退化防护** | 无 | 无 | 无 | **_best_snapshot 回滚** |
| **振荡检测** | 无 | 无 | 无 | **三重指纹振荡检测** |
| **执行器约束** | 无 | 无 | 无 | **RepairMode + Patch 限幅 + Formal Guards** |
| **作弊检测** | 无 | 无 | 无 | **Bypass Guard 精确匹配** |
| **可审计性** | 无 | 无 | 无 | **全事件文件化存储** |
| **私有化部署** | SaaS | SaaS | SaaS/本地 | **全文件化，零中间件，支持离线** |

### 7.4 商业价值

- **填补"L4 设计驱动开发"私有化部署空白**：全球只有 Devin 等极少数产品具备类似能力，且全部是 SaaS
- **企业私有化部署**：全文件化架构，零外部中间件，支持本地 LLM（glm-4.7-fp8），数据不出域
- **Bug 修复自动化**：实测 47.2% 的开发任务是 Bug 修复，ASR 的自动修复-验证-收敛循环直接命中最高频痛点

---

## 八、落地部署方案

### 8.1 部署方式

```bash
git clone <repo>
cd asr
pip install -r requirements.txt
python -m asr.cli.main run --project ./my_project --max-iterations 10
```

### 8.2 依赖环境

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.12.9 | 核心运行时 |
| OpenCode CLI | >= 1.15 | LLM 调用层 |
| oh-my-openagent | >= 3.17（推荐） | 多智能体编排 |
| pytest | >= 7.0 | 测试执行 |
| pydantic | >= 2.0 | 数据模型 |
| click | >= 8.0 | CLI 界面 |
| pyyaml | >= 6.0 | 配置解析 |
| filelock | >= 3.0 | 原子写入 |

**无需**：数据库、消息队列、Docker、云服务、git

### 8.3 模型兼容性

| 模型 | 状态 | 说明 |
|------|------|------|
| **glm-4.7-fp8** | ✅ **实际使用** | 200K 上下文，本地部署 |
| 其他 OpenAI 兼容接口 | ✅ 兼容 | 通过环境变量配置 |

### 8.4 运维注意事项

1. **磁盘空间**：`.runtime/` 下写入事件、日志，建议定期清理
2. **并发运行**：同一项目目录不支持同时运行多个 ASR 实例
3. **Token 预算**：通过 `--max-iterations` 控制最大迭代次数
4. **Sandbox 清理**：Tester/Analyzer 执行后自动清理 `.asr_sandbox/`

---

## 九、端到端验证

### 9.1 计算器项目验证

使用最小化计算器项目进行端到端验证：

| 阶段 | 状态 | 说明 |
|------|------|------|
| ASR 启动 | ✅ | 无 import 错误、无语法错误 |
| Builder 第1轮 | ✅ | opencode 成功生成 `calculator.py`（add/subtract/multiply/divide + 除零异常） |
| Tester 第1轮 | ✅ | 生成 5 个测试文件（基础/边界/类型/属性/特殊值），173 个测试全部通过 |
| Tester 第2轮 | ✅ | 重新确认 173 passed |
| Analyzer | ✅ | 生成验收报告，结论 ALL CLEAR，逐项核对 DESIGN.md 所有需求已实现 |

### 9.2 可研报告编译器 Demo

- **输入**：13k token 设计文档（DESIGN.md，可研报告编译器 v4.3）
- **输出**：完整可运行代码工程（runtime/ 8,343 行，15 文件 + tests/）
- **迭代**：10 轮收敛循环
- **模型**：glm-4.7-fp8（200K 上下文，本地部署）

### 9.3 控制论优化验证

六轮第一性原理推演修复的关键问题：

| 轮次 | 问题 | 严重度 | 修复 |
|------|------|--------|------|
| 第四轮 | _best_snapshot 保存空列表 | 致命 | 新增 `_snapshot_project_files()` 直接快照项目文件 |
| 第四轮 | Guard 2 遗漏新建文件 | 高 | 增加 2b 分支扫描新 .py 文件 |
| 第四轮 | OSCILLATION_BREAK 无退出 | 中 | improving_streak >= 2 时退出 |
| 第五轮 | circuit breaker 误杀缓慢改善 | 致命 | 改为 `pass_rate[-1] <= pass_rate[-2]` |
| 第五轮 | inline rollback 破坏反馈链 | 中 | 删除 inline rollback，由 REGRESSION_RECOVERY 统一处理 |
| 第五轮 | Guard 3 bypass 误报 | 中 | 改为精确行级匹配 |
| 第六轮 | REGRESSION_RECOVERY 无退出+每轮回滚 | 致命 | 只在 regressing_streak>=2 时回滚；improving>=1 退出 |
| 第六轮 | FINAL_VERIFICATION 无退出 | 致命 | Analyzer 发现问题→退出到 SPEC_COMPLETION/TEST_FIX |
| 第六轮 | mode_changed 误判 | 高 | 改用 `_prev_mode_for_feedback` 直接追踪 |
| 第六轮 | Guard 3 路径检查错误 | 中 | 从 diff header 追溯文件名 |

### 9.4 测试结果

- 6 个核心文件全部通过 `ast.parse()` 语法检查
- controller 测试：20 passed, 4 pre-existing failures（引用已移除的旧方法名）
- GLM-4.7-FP8 端点：37/37 API 测试通过，零 400 错误
- 端到端运行：无 crash，Builder → Tester → Analyzer 流程正常衔接

---

## 附录

### A. 系统文件结构

```
asr/
├── asr/
│   ├── cli/main.py              # CLI 入口
│   ├── controller/convergence.py # 收敛状态机 + 控制论指标（核心，~1350行）
│   ├── agents/
│   │   ├── builder.py           # BuilderAgent（有状态会话延续）
│   │   ├── tester.py            # TesterAgent（Sandbox + 测试生成）
│   │   ├── analyzer.py          # AnalyzerAgent（diff-only + 结构化分析）
│   │   ├── opencode_backend.py  # OpenCode CLI 子进程调用
│   │   └── llm_tracker.py       # Token 追踪
│   ├── dag/                     # DAG 并行执行
│   ├── events/                  # 19 种事件类型 + EventStore
│   ├── config/models.py         # ASRConfig（含控制论参数）
│   └── runtime.py               # ASRRuntime（编排入口）
├── tests/                       # 单元测试
├── demo_dev/                    # Demo 工程
└── requirements.txt
```

### B. 核心收敛终止条件

| 终止条件 | 触发机制 | 实现状态 |
|---------|---------|---------|
| 测试通过 + 语义对齐 | `passed_all AND spec_aligned` 连续3轮 → CONVERGED | ✅ 已实现 |
| 最大迭代次数 | `iteration >= max_iterations` → STUCK | ✅ 已实现 |
| Circuit breaker | `pass_rate 连续N轮无改善` → STUCK | ✅ 已实现 |
| 退化回滚 | `regressing_streak >= 2` → REGRESSION_RECOVERY | ✅ 已实现 |
| 振荡检测 | `oscillation_score >= 0.7` → OSCILLATION_BREAK | ✅ 已实现 |
| 失败指纹重复 | `repeated_failure_count >= 3` → oscillation_score 提升 | ✅ 已实现 |

### C. 开发任务统计背景数据

基于 WorkBuddy 工具统计的 36 个开发任务（2026-04-14 至 04-23）分布：

| 任务类型 | 数量 | 占比 |
|---------|------|------|
| 发现 Bug | 17 | 47.2% |
| 新需求 | 7 | 19.4% |
| Review | 6 | 16.7% |
| 改需求 | 5 | 13.9% |
| 需求未实现 | 2 | 5.6% |
| 其他 | 2 | 5.6% |

### D. Runtime 目录结构

```
.runtime/
├── events/          # 所有事件 JSON 文件（FileLock 原子写入）
├── logs/            # asr.log（收敛日志）+ llm.jsonl（Token 追踪）
├── patches/         # 存储的 patch 文件
├── diffs/           # 存储的 diff 文件
├── state/           # 最终状态快照（CONVERGED/STUCK 时写入）
├── tasks/           # 任务状态持久化
└── inbox/           # ★ 动态创建：Controller 写入，AgentRunner 轮询
    ├── builder/
    ├── tester/
    └── analyzer/
```

### E. 配置模型（asr/config/models.py）

```
ASRConfig
├── default_model: str          # 默认模型名
├── agents: list[AgentConfig]   # Agent 配置列表
│   ├── role: builder|tester|analyzer|security|performance|architecture
│   ├── model: ModelConfig      # 模型参数
│   │   ├── model, temperature, max_tokens
│   │   ├── api_key, api_base, timeout, num_retries
│   ├── system_prompt: str      # 系统提示词
│   └── max_context_messages: int
├── convergence: ConvergenceConfig
│   ├── max_iterations: int (默认5)
│   ├── stable_diff_threshold: int
│   ├── patch_oscillation_threshold: int
│   ├── test_timeout: int
│   ├── circuit_breaker_threshold: int          # v2.0 新增
│   ├── max_files_per_patch: int                # v2.0 新增
│   ├── max_lines_per_patch: int                # v2.0 新增
│   └── error_score_weights: dict               # v2.0 新增
└── runtime: RuntimeConfig
    ├── event_dir, inbox_dir, patch_dir, state_dir
```

`.env` 自动加载：

```ini
FEASIBILITY_LLM_MODEL=your-model-name
FEASIBILITY_LLM_API_BASE=http://localhost:8000/v1
FEASIBILITY_LLM_API_KEY=your-api-key
FEASIBILITY_LLM_CONTEXT=131072
ASR_OPENCODE_TIMEOUT=24400
ASR_VERBOSE=1
```

### F. 日志格式

**收敛日志（asr.log）**：

```
[14:32:15] [INFO ] [controller  ] iter=  1 errors=0 phase=REPAIRING   patches=1 files=3 lines=156 init
[14:33:22] [INFO ] [controller  ] iter=  2 errors=3 phase=TESTING     passed=12/15 fail=test_foo,test_bar
[14:33:22] [CONV ] [controller  ] iter=  2 errors=3 phase=TESTING     pass_rate=0.80 trend=regressing
[14:35:10] [INFO ] [controller  ] RepairMode: TEST_FIX → REGRESSION_RECOVERY (regressing_streak=2)
```

**LLM 追踪（llm.jsonl）**：

```json
{"agent": "builder", "model": "glm-4.7-fp8", "prompt_tokens": 12345, "completion_tokens": 4512, "total_tokens": 16857, "timestamp": 1716732000.123}
{"agent": "tester", "model": "glm-4.7-fp8", "prompt_tokens": 8123, "completion_tokens": 2341, "total_tokens": 10464, "timestamp": 1716732100.456}
```

### G. 关键设计原则

**原则 1：裁决 Agent 必须无状态** — Tester、Analyzer 每轮重新分析，防止错误累积。

**原则 2：Builder 允许长期上下文** — Builder 负责长任务连续性，通过 OpenCode Session 延续。

**原则 3：永远不要让 AI 自己定义成功** — 必须外部验证（pytest + 语义分析）。

**原则 4：局部修复优于全局重写** — 全量重生成最容易漂移，Diff 驱动修复是成本控制核心。

**原则 5：收敛优于智能** — ASR 的核心不是更聪明，而是更稳定。稳定的软件系统 = 弱智能 + 强约束。

---

*本报告对应系统版本：ASR v2.0 | 文档同步日期：2026-07-06*
