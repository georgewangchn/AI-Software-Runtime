# AI Software Runtime (ASR) 系统设计文档

> 基于 OpenCode 的 Python 原生自治式 AI 软件工程运行时（Implemented Architecture — 同步于 2026-05-26）

---

**版本历史**

| 版本 | 日期 | 核心变更 |
|------|------|---------|
| v1.0 | 2026-04 | 初始设计：收敛循环、双层裁决、6 Agent 架构 |
| v1.1 | 2026-05-26 | **系统同步**：补充实际实现的 CLI、DAG、OpenCode 后端、Sandbox、Logger、配置系统；标记 Phase 4（Verification Mesh）为规划中；修正状态机顺序和运行时目录结构 |

---

## 一、项目定义（Definition）

AI Software Runtime（ASR）是一套**面向 AI 编程任务的自治式软件工程运行时**。

其核心目标不是让 AI 更会写代码，而是让 AI 生成的软件能够**稳定收敛**：

```
Generate → Verify → Diff → Repair → Converge
```

ASR 本质上：

- 不是 ChatBot
- 不是 Prompt Workflow
- 是 **Agent Framework + Convergence Runtime**，即带有收敛循环的多 Agent 协作系统

---

## 二、核心问题（Why）

当前 AI 编程系统存在四个根本问题：

| 问题 | 本质 |
|------|------|
| 长任务漂移 | 无收敛机制 |
| 修复破坏旧功能 | 无全局验证 |
| 需求偏离 | 无语义裁决 |
| 无限循环修复 | 无终止条件 |

核心问题并不是"模型不够强"，而是**缺少工程级约束系统**。

因此，ASR 的目标不是提升模型能力，而是构建 AI 软件工程运行时。

---

## 三、第一性原理（First Principles）

### 3.1 软件开发的本质

软件开发本质不是写代码，而是**持续减少"实现"与"需求"之间的差异**：

```
Software Development = Continuous Diff Reduction
```

```
需求 → 实现 → 验证 → 发现差异 → 修复差异 → 收敛
```

因此：**软件工程本质是收敛系统**。

### 3.2 AI Coding 的根本缺陷

当前 AI Coding 本质还是 Next Token Prediction，而不是 Convergence Runtime。

因此 AI 能生成代码，但无法保证：

- 正确
- 完整
- 不漂移
- 可维护
- 可持续修复

### 3.3 ASR 核心哲学

ASR 基于**"约束大于智能"**：

```
稳定的软件系统 = 弱智能 + 强约束
```

而不是 `超强模型 = 可靠工程`。

---

## 四、系统核心思想（Core Philosophy）

### 4.1 Generate ≠ Correct

LLM 只能生成候选解，不能保证正确性。因此所有生成结果必须验证：

```
Generate → Verify → Diff → Repair → Re-Verify → Converge
```

### 4.2 去中心化认知

ASR 不允许同一个 Agent 既生成又裁决自己，因为**生成者无法可靠审判自己**。认知职责必须拆分。

### 4.3 软件工程化 AI

ASR 将 Prompt Engineering 升级为 Runtime Engineering：

| AI 概念 | ASR 对应 |
|---------|---------|
| Prompt | Spec |
| Chat | Workflow |
| Agent | Runtime Node |
| Context | Runtime State |
| Retry | Repair Loop |
| Reflection | Verification |
| Memory | Event State |

---

## 五、系统总体架构（Architecture）

### 5.1 总体结构（已实现）

```
                         ┌─────────────────────┐
                         │     ASR CLI          │
                         │  run / run-dag / init│
                         └──────────┬──────────┘
                                    │
                          ┌─────────▼─────────┐
                          │   ASRRuntime      │
                          │  (编排入口)        │
                          └─────────┬─────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
    │  ASRController  │  │  DAGExecutor    │  │  AgentOrchestrator  │
    │  (直接模式)      │  │  (DAG 并行模式)  │  │  (解耦 A2A 模式)    │
    └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘
             │                    │                      │
             └────────────────────┼──────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
    ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐
    │ BuilderAgent │   │ TesterAgent  │   │ AnalyzerAgent        │
    │  ✅ 已实现    │   │  ✅ 已实现    │   │  ✅ 已实现             │
    └──────┬───────┘   └──────┬───────┘   └──────┬───────────────┘
           │                  │                  │
           └──────────────────┼──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   OpenCode CLI    │
                    │ (subprocess 调用)  │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
  │ EventStore   │   │ PatchEngine  │   │ ASRLogger +      │
  │ (事件/A2A)   │   │ (unified diff)│   │ LLMTracker       │
  └──────────────┘   └──────────────┘   └──────────────────┘

  ┌──────────────────────────────────────────────────────────┐
  │  🔮 Phase 4 规划：Verification Mesh                      │
  │  SecurityAgent / PerformanceAgent / ArchitectureAgent    │
  └──────────────────────────────────────────────────────────┘
```

---

## 六、系统定位（System Position）

**OpenCode 负责**：
- LLM 调用与 Prompt 执行
- Tool Calling
- Agent 执行（Session 延续）
- Context 管理

**ASR Controller 负责**：
- 收敛循环状态机驱动
- Agent 编排（直接调用 / 解耦 A2A）
- Patch 管理与回滚裁决
- 终止条件评估
- 事件审计

**ASR Agents 负责**：
- BuilderAgent：代码生成 / Patch 修复（通过 OpenCode CLI）
- TesterAgent：测试生成 + pytest 执行（Sandbox 隔离）
- AnalyzerAgent：语义分析（Sandbox 隔离，YAML 输出）

**ASR 基础设施负责**：
- EventStore：文件化事件存储 + Inbox 轮询 + 事件回放
- PatchEngine：unified diff 解析/应用/回滚
- DAG System：任务拆解、拓扑排序、并行执行
- Logger + LLMTracker：收敛日志、Token 追踪

---

## 七、核心模块（Core Agents）

### 7.1 BuilderAgent（构建Agent）✅ 已实现

**职责**：
- 代码生成（通过 OpenCode CLI 委派）
- Patch 修复（基于测试失败信息生成 unified diff）
- 初始项目搭建（读取 DESIGN.md 生成初始代码）

**特点**：
- 可保留长期上下文（OpenCode Session 延续，`--continue` 模式）
- Builder 是系统唯一允许长期状态的 Agent
- 通过 `opencode_backend.py` 的 subprocess 调用 OpenCode CLI

### 7.2 TesterAgent（测试裁决Agent）✅ 已实现

**职责**：
- 使用 OpenCode 自动生成 pytest 测试代码
- 在 Sandbox（`.asr_sandbox/tester/`）中隔离执行 pytest
- 将生成的测试文件回写到项目 `tests/` 目录
- 解析 pytest 输出（`--tb=short` 模式）为结构化结果

**输出示例**：

```json
{
  "total": 15,
  "passed": 12,
  "failed": 3,
  "errors": 0,
  "failures": [
    {"nodeid": "tests/test_xxx.py::test_foo", "message": "AssertionError"}
  ]
}
```

**特点**：
- Stateless：每轮重新分析，防止错误污染
- Sandbox 隔离：不污染项目工作目录
- 测试持久化：生成的测试文件写回项目，下次直接复用

### 7.3 AnalyzerAgent（语义裁决Agent）✅ 已实现

**职责**：
- 对比 DESIGN.md 与实现代码
- 在 Sandbox（`.asr_sandbox/analyzer/`）中执行
- 输出 `analysis.yaml`：missing_features / logic_issues / constraint_violations
- 支持 severity 标记（critical/high → 阻止收敛）

**输出示例**：

```json
{
  "task_type": "dev",
  "missing_features": ["未实现XXX功能"],
  "logic_issues": ["YYY逻辑错误"],
  "constraint_violations": ["违反ZZZ约束"]
}
```

**作用**：第二层语义裁决。分析结果通过 AnalyzerFeedbackEvent 反馈给 BuilderAgent 进行修复。

### 7.4 SecurityAgent / PerformanceAgent / ArchitectureAgent 🔮 规划中

属于 Phase 4 "Verification Mesh"（多维裁决网络）。当前已在 AgentName 枚举和 MeshVerdictEvent 中预留接口，但无实际实现。规划中由这三个 Agent 提供安全审查、性能分析和架构合规检查，形成多维度裁决网络。

---

## 八、双层裁决系统（Layered Verification）

这是 ASR 最核心的创新。

**第一层：硬约束裁决** — 验证代码是否正确运行

- pytest
- 编译
- lint
- coverage
- runtime error

由 **TesterAgent** 负责。

**第二层：语义裁决** — 验证实现是否符合需求

- 功能遗漏
- 逻辑偏差
- Spec 不一致
- 错误实现

由 **AnalyzerAgent** 负责。

---

## 九、系统运行机制（Runtime）

### 9.1 核心收敛循环

系统本质是：

```
Generate → Verify → Diff → Repair → Verify → Converge
```

而不是 `Prompt → Output`。

### 9.2 Runtime 控制逻辑与状态机

Controller 驱动以下状态机收敛循环（已实现顺序）：

```
States:  INIT → REPAIRING → TESTING → ANALYZING → CONVERGED / STUCK
```

**每轮迭代**：

1. **REPAIRING**：BuilderAgent 生成/修复代码
   - 首轮：读取 DESIGN.md，生成初始代码（无测试失败信息）
   - 后续：基于上一轮的测试失败 + 语义分析反馈生成 Patch
   - Controller 在修复前自动创建 rollback 快照（所有 `.py` 文件原内容）

2. **TESTING**：TesterAgent 在 Sandbox 中执行测试
   - 复制项目文件到 `.asr_sandbox/tester/`
   - OpenCode 生成 pytest 测试 → 运行 pytest
   - 解析结果，持久化测试文件回项目

3. **若测试通过** → ANALYZING：
   - AnalyzerAgent 语义分析（Sandbox 隔离）
   - 若 spec_aligned → CONVERGED
   - 若发现偏差 → 下一轮 REPAIRING（传入 findings）

4. **若测试失败** → 下一轮 REPAIRING（传入 failures）

**回滚机制**：若 patch 导致测试失败数增加（退化），Controller 自动回滚：
- 恢复所有被修改文件到修补前内容
- 删除修补过程中新增的非测试 `.py` 文件
- 这是针对 Builder 不可靠生成的关键安全机制

### 9.3 收敛终止条件

| 条件 | 作用 | 实现状态 |
|------|------|---------|
| 最大迭代次数 | 防止无限循环 | ✅ 已实现（max_iterations，默认5） |
| Diff稳定 | 相同 patch 连续出现 N 次 → STUCK | ⚠️ 配置已定义（stable_diff_threshold），Controller 未接入 |
| Patch震荡 | 两个 patch 交替出现 → STUCK | ⚠️ 配置已定义（patch_oscillation_threshold），Controller 未接入 |
| Patch失败 | patch 应用失败 → STUCK | ⚠️ 预留，当前自动回滚处理 |
| 测试通过 + Spec一致 | 全部通过 → CONVERGED | ✅ 已实现 |

### 9.4 Controller 职责与边界

ASRController 是系统的主动编排引擎，不是薄适配层。

**Controller 负责**：
- 收敛循环状态机：驱动 INIT → REPAIRING → TESTING → ANALYZING → CONVERGED/STUCK
- Agent 编排：直接调用（agent.process）或解耦 A2A（AgentRunner 轮询 inbox）
- Patch 管理：通过 PatchEngine 应用 unified diff 到项目文件
- 回滚裁决：检测退化（after_count > before_count）→ 自动回滚
- 终止裁决：max_iterations + spec_aligned 条件
- 事件审计：所有状态转换产生结构化事件（完整审计轨迹）
- Progress Callback：支持外部进度回调（CLI 实时显示）

**Controller 不负责**：
- 代码生成（BuilderAgent → OpenCode CLI）
- 测试生成与执行（TesterAgent）
- 语义分析（AnalyzerAgent）
- 安全/性能/架构分析（🔮 Phase 4 规划）

---

## 十、本地化 A2A（Agent-to-Agent）

ASR 不采用 Kafka / NATS / 微服务 / 分布式总线，MVP 阶段复杂度过高。因此 ASR 使用**文件化 A2A 协议**。

### 10.1 Event File

所有 Agent 通信统一通过结构化事件文件：

```json
{
  "event_id": "uuid",
  "task_id": "task_001",
  "type": "TEST_FAILED",
  "from": "tester",
  "to": "controller",
  "payload": {
    "total": 15,
    "passed": 12,
    "failed": 3,
    "failures": [
      {"nodeid": "test_xxx", "message": "AssertionError"}
    ]
  }
}
```

**完整事件类型（已实现 20 种）**：

TaskCreated, CodeGenerated, TestStarted, TestFailed, TestPassed, TestError, SpecDiffFound, SpecAligned, PatchRequested, PatchGenerated, PatchApplied, PatchFailed, PatchRolledBack, AnalyzeRequested, AnalyzerFeedback, ConvergenceIteration, Converged, Stuck, ErrorOccurred, MeshVerdict

### 10.2 Runtime 目录结构（实际）

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

### 10.3 两种 A2A 通信模式

**1. 直接调用模式（默认）**：

Controller 直接调用 `agent.process(event)`，Agent 返回结果事件列表。Controller 将结果写入 EventStore 和 Inbox（供审计与回放）。

**2. 解耦模式（--decoupled）**：

AgentRunner 独立异步轮询 inbox/ 目录。AgentOrchestrator 管理所有 AgentRunner 的生命周期。两种模式产生相同的事件流，可在运行时切换。

AgentRunner 实现：
- asyncio poll loop（默认 0.1s 间隔）
- 去重：processed_ids 集合防止重复处理
- 异常隔离：单个 Agent 异常不影响其他 Runner

AgentOrchestrator 实现：
- `register()`：注册 AgentRunner
- `start_all()` / `stop_all()`：批量启停
- `run_until_converged()`：带超时的收敛等待

**核心原则**：Agent 的**认知职责**分离（Builder ≠ Tester ≠ Analyzer），而非通信介质分离。

---

## 十一、状态系统（State System）

### 11.1 为什么不能依赖 Context

LLM Context：
- 不稳定
- 会污染
- 会漂移
- 会遗忘

因此 Runtime 状态必须**外部化**。

### 11.2 Event-based State

系统真实状态来源于**事件流**：

```
TaskCreated → CodeGenerated → TestFailed → PatchGenerated → SpecRejected → PatchAccepted
```

Runtime 根据事件重建系统状态。

---

## 十二、Spec 系统（Specification System）

### 12.1 Spec 输入方式

ASR 支持两种 Spec 输入方式：

1. **结构化 YAML（推荐，Primary）**：直接编写 YAML spec 文件，可靠性最高。示例见 `demo_project/spec.yaml`。

2. **自然语言编译（Convenience）**：通过 SpecCompiler 将自然语言需求编译为 Structured Spec，适用于快速原型，但结果需人工审核。

### 12.2 为什么必须结构化 Spec

无结构需求无法验证——这是 AI Coding 最大问题之一。

---

## 十三、Diff 驱动修复（Diff-driven Repair）

ASR 不直接重新生成整个项目，而是基于 Diff 局部修复：

```
发现差异 → 生成Patch → 验证Patch → 收敛
```

这是**成本控制的核心**。

---

## 十四、系统阶段路线（Roadmap）

**Phase 1：Single Runtime MVP** ✅ 已实现

实现 `Generate → Verify → Repair` 能力：
- BuilderAgent（OpenCode CLI 委派）
- TesterAgent（Sandbox 隔离测试）
- AnalyzerAgent（语义分析）
- ASRController（收敛状态机）
- EventStore（事件存储/回放）
- PatchEngine（unified diff 解析/应用/回滚）

**Phase 2：File-based A2A** ✅ 已实现

增加：
- Event Log（完整事件类型体系，20 种事件）
- Inbox（动态创建，AgentRunner 轮询）
- Event Replay（EventStore.replay_events）
- 双模式 A2A（直接调用 / 解耦轮询）
- AgentOrchestrator（多 Runner 编排）

实现本地自治 Runtime。

**Phase 3：Task DAG** ✅ 已实现

增加：
- TaskDecomposer（从 Spec.features / test failures 拆解子任务）
- TaskDAG（拓扑排序、环检测、文件冲突解决）
- DAGExecutor（asyncio.gather 并行执行）
- CLI: `asr run-dag` 命令

能力：子任务级收敛。

**Phase 4：Verification Mesh** 🔮 规划中

增加 SecurityAgent / PerformanceAgent / ArchitectureAgent，形成多维裁决网络。当前状态：AgentName 枚举和 MeshVerdictEvent 已预留接口。

**Phase 5：Autonomous Engineering Runtime** 🔮 规划中

最终 ASR 成为 OpenCode 的自治工程运行时层。

---

## 十五、关键设计原则（Critical Principles）

**原则 1：裁决Agent必须无状态**

Tester、Analyzer 每轮重新分析，防止错误累积。

**原则 2：Builder允许长期上下文**

Builder 负责长任务连续性。

**原则 3：永远不要让 AI 自己定义成功**

必须外部验证。

**原则 4：局部修复优于全局重写**

全量重生成最容易漂移。

**原则 5：收敛优于智能**

ASR 的核心不是更聪明，而是更稳定。

---

## 十六、技术栈（Tech Stack）

严格限制：仅 Python。

| 模块 | 技术 |
|------|------|
| Runtime | Python 3.10+ |
| Agent Backend | OpenCode CLI（subprocess 调用，Session 延续，Git diff 提取） |
| 状态存储 | JSON / YAML（FileLock 原子写入） |
| Patch系统 | unified diff（Python 解析 + subprocess patch 命令 fallback） |
| 测试 | pytest（--tb=short 模式，Sandbox 隔离） |
| Sandbox | subprocess + shutil（.asr_sandbox/ 目录） |
| Event State | 文件系统（.runtime/events/ + inbox/） |
| CLI | Click + Rich（进度显示、Token 追踪） |
| 数据模型 | Pydantic v2（事件、配置、Spec） |
| 配置 | YAML + .env（FEASIBILITY_LLM_* 自动加载） |
| 日志 | 文件日志（asr.log + llm.jsonl） |
| 预留 | FastAPI + uvicorn（Phase 5 API 服务预留） |

---

## 十七、核心价值（Value）

**相比单 Agent**，ASR：
- 更稳定
- 可收敛
- 可验证
- 不易漂移

**相比 Claude Code 类系统**，ASR：
- 更低成本
- 更强工程约束
- 更可控
- 可私有化

---

## 十八、最终系统本质（Final Definition）

ASR 本质不是 AI Coding Tool，而是 **AI Software Convergence Runtime**。

即：一个让 AI 软件开发从"生成问题"变成"工程收敛问题"的运行时系统。

---

## 十九、最终结论（Conclusion）

ASR 的核心创新不是"让 AI 更强"，而是"让 AI 在工程约束下稳定收敛"。

最终实现：

```
低成本模型 + 多Agent协作 + 验证驱动 + 差异修复 + 工程约束 = 高稳定性 AI 软件开发系统
```

---

## 二十、CLI 命令行接口

ASR 通过 Click 框架提供命令行入口（`asr/cli/main.py`）。

### 20.1 命令列表

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `asr run` | 单项目收敛执行 | --project（必需）, --spec, --max-iterations, --decoupled, --verbose |
| `asr run-dag` | DAG 模式执行 | --project（必需）, --spec（必需） |
| `asr init` | 初始化 ASR 项目 | --project（必需） |
| `asr compare` | 对比基线（demo） | --project, --spec, --baseline |

### 20.2 run 命令详情

```bash
python -m asr.cli.main run \
  --project /path/to/project \
  --spec /path/to/spec.yaml \     # 可选，省略则读取 DESIGN.md
  --max-iterations 10 \           # 覆盖配置中的 max_iterations
  --decoupled \                    # 使用解耦 A2A 模式
  --verbose
```

**输出示例**：

```
ASR Runtime [direct]
Project: /path/to/project
Spec: /path/to/spec.yaml
Max iterations: 10

  [  1] Builder   errors= 0  🔧  | tok: 12.3k/4.5k  | init
  [  2] Tester    errors= 3  ❌  | tok: 8.1k/2.3k   | passed=12/15 fail=test_foo,test_bar
  [  3] Builder   errors= 3  🔧  | tok: 5.2k/1.8k   | fixing=3
  [  4] Tester    errors= 0  ✅  | tok: 3.1k/1.2k   | passed=15/15
  [  5] Analyzer  errors= 0  ✅  | aligned

✅ CONVERGED
Iterations: 5 | Events: 23

📁 详细日志: .runtime/logs/asr.log
📁 LLM 追踪: .runtime/logs/llm.log
```

每行输出包含：
- 迭代编号
- 当前阶段（Builder / Tester / Analyzer）
- 剩余错误数
- 状态图标（🔧修复中 / ❌失败 / ✅通过）
- Token 消耗（prompt/completion）
- 阶段详情

### 20.3 init 命令详情

```bash
python -m asr.cli.main init --project /path/to/project
```

自动创建：
- `asr_config.yaml`（默认配置）
- `.runtime/` 目录结构（events, inbox/builder, inbox/tester, inbox/analyzer, tasks, patches, diffs, state）

---

## 二十一、Task DAG 系统 ✅ 已实现

### 21.1 设计目标

将大型任务拆解为多个子任务（TaskNode），构建依赖 DAG，并行执行收敛循环。

### 21.2 核心模型

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
- 完成判定：`all_done()`（所有节点为终止状态）

### 21.3 TaskDecomposer（任务拆解）

两种拆解策略：

1. **基于 Spec.features 拆解（特征驱动）**：
   - 每个 feature 生成一个 TaskNode
   - 通过文件名匹配推断 files 关联（`_infer_files`）
   - 有文件冲突的节点建立依赖关系

2. **基于测试失败拆解（修复驱动）**：
   - 按失败文件的模块分组
   - 每个分组生成一个修复节点
   - 有文件冲突的节点建立依赖关系

### 21.4 DAGExecutor（并行执行）

```python
while not dag.all_done():
    ready = dag.get_ready_nodes()     # 获取所有依赖已满足的节点
    for node in ready:
        dag.nodes[node.id].status = RUNNING
    tasks = [asyncio.gather(*(_run_node(dag, n, spec) for n in ready))]
    await tasks                       # 并行执行所有就绪节点
```

每个节点的执行：
- 构建节点专用 Specification（合并 base spec + 节点特定约束）
- 创建独立 ASRController 实例
- 运行完整收敛循环
- 记录结果（CONVERGED / STUCK）

### 21.5 CLI 使用

```bash
python -m asr.cli.main run-dag --project /path --spec spec.yaml
```

**输出示例**：

```
ASR Runtime [DAG Mode]
Nodes: 5 | Converged: 4 | Stuck: 1
Total iterations: 27
  ✅ dag-0-f0: converged
  ✅ dag-0-f1: converged
  ✅ dag-0-f2: converged
  ❌ dag-0-f3: stuck
  ✅ dag-0-f4: converged
```

---

## 二十二、OpenCode 后端与 Sandbox 隔离执行

### 22.1 OpenCode Backend（asr/agents/opencode_backend.py）

所有 ASR Agent 通过 subprocess 调用 OpenCode CLI 完成实际工作。

**核心函数**：

- `opencode_completion(prompt, project_dir)`：TesterAgent 和 AnalyzerAgent 使用
  - 调用 `opencode run --model <model> --format json --dir <dir>`
  - 解析 JSON 输出获取 session ID 和 token 统计

- `opencode_diff(prompt, project_dir, session_id)`：BuilderAgent 使用
  - 支持 `--continue` 模式（session 延续，保留长期上下文）
  - 通过 `git diff --cached HEAD` 提取变更的 unified diff
  - 自动 git commit 变更

### 22.2 BuilderAgent 的 Session 延续

BuilderAgent 是唯一允许长期上下文的 Agent：
- 首次调用：不传 session_id → OpenCode 创建新 session
- 后续调用：传入上次返回的 session_id + `--continue` → 在同一 session 中继续
- 效果：Builder 能"记住"之前的修改历史和项目状态

### 22.3 Sandbox 隔离执行

TesterAgent 和 AnalyzerAgent 使用 Sandbox 模式防止污染：

**TesterAgent 执行流程**：

```
1. 清理 .asr_sandbox/tester/
2. 复制项目文件到 sandbox（排除 .asr_sandbox, .git, .runtime, .pytest_cache）
3. OpenCode 在 sandbox 中生成 pytest 测试文件
4. 运行 pytest -v --tb=short（600s 超时）
5. 解析 pytest 输出为结构化结果
6. 将生成的测试文件从 sandbox 回写到项目 tests/
7. 清理 sandbox
```

**AnalyzerAgent 执行流程**：

```
1. 清理 .asr_sandbox/analyzer/
2. 复制项目文件到 sandbox
3. OpenCode 在 sandbox 中分析，输出 analysis.yaml
4. 解析 YAML 为 AnalysisReport
5. 清理 sandbox
```

---

## 二十三、日志与可观测性

### 23.1 ASRLogger（.runtime/logs/asr.log）

记录收敛循环的关键节点：

```
[14:32:15] [INFO ] [controller  ] iter=  1 errors=0 phase=REPAIRING   patches=1 files=3 lines=156 init
[14:33:22] [INFO ] [controller  ] iter=  2 errors=3 phase=TESTING     passed=12/15 fail=test_foo,test_bar
[14:33:22] [CONV ] [controller  ] iter=  2 errors=3 phase=TESTING     passed=12/15 fail=test_foo
[14:35:10] [INFO ] [controller  ] iter=  3 errors=3 phase=REPAIRING   patches=1 files=4 lines=210 fixing=3
```

### 23.2 LLMTracker（.runtime/logs/llm.jsonl）

每次 Agent 调用 LLM 后记录 token 使用：

```json
{"agent": "builder", "model": "opencode/qwen3-next-80b", "prompt_tokens": 12345, "completion_tokens": 4512, "total_tokens": 16857, "timestamp": 1716732000.123}
{"agent": "tester", "model": "opencode/qwen3-next-80b", "prompt_tokens": 8123, "completion_tokens": 2341, "total_tokens": 10464, "timestamp": 1716732100.456}
```

同时维护内存计数器，CLI 可实时展示每 Agent 的累计 token 消耗。

---

## 二十四、配置与启动

### 24.1 配置模型（asr/config/models.py）

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
│   └── test_timeout: int
└── runtime: RuntimeConfig
    ├── event_dir, inbox_dir, patch_dir, state_dir
```

### 24.2 .env 自动加载

系统从 `.env` 文件自动读取以下变量：

```ini
FEASIBILITY_LLM_MODEL=your-model-name
FEASIBILITY_LLM_API_BASE=http://localhost:8000/v1
FEASIBILITY_LLM_API_KEY=your-api-key
FEASIBILITY_LLM_CONTEXT=131072
ASR_OPENCODE_TIMEOUT=24400
ASR_VERBOSE=1
```

`create_default_config()` 从 `.env` 构建默认配置，无需手动编写 YAML。

### 24.3 启动方式

```bash
# 方式 1：CLI 直接启动（推荐）
python -m asr.cli.main run --project ./my_project --max-iterations 10

# 方式 2：初始化新项目后运行
python -m asr.cli.main init --project ./my_project
python -m asr.cli.main run --project ./my_project --spec ./my_project/spec.yaml
```

### 24.4 项目文件布局

```
my_project/
├── DESIGN.md              # 设计文档（必需，Agent 读取）
├── spec.yaml              # 结构化 Spec（可选，优先于 DESIGN.md）
├── *.py                   # 源代码文件
├── tests/                 # 测试文件（可空，TesterAgent 自动生成）
├── .runtime/              # ASR 运行时数据（自动创建）
└── asr_config.yaml        # ASR 配置（可选，asr init 自动生成）
```

---

## 附件

某开发（WorkBuddy）任务类型分布（36个任务，04-14 ~ 04-23）：

| 类型 | 数量 | 占比 |
|------|------|------|
| 发现Bug | 17 | 43.6% |
| 新需求 | 7 | 23.1% |
| Review | 6 | 15.4% |
| 改需求 | 5 | 10.3% |
| 需求未实现 | 2 | 5.1% |
| 其他 | 2 | 5.1% |
