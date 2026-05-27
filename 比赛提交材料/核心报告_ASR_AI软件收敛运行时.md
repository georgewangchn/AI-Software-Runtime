# AI Software Runtime（ASR）
## 自治式 AI 软件工程收敛运行时

**工程实践报告**

---

| 项目信息 | |
|---------|--|
| 项目名称 | AI Software Runtime（ASR）—— 自治式 AI 软件工程收敛运行时 |
| 赛道方向 | AI + 研发（考察规范驱动开发、多模态情境智能及研发效率提升能力） |
| 报告版本 | v1.3 |
| 系统版本 | ASR v1.1（同步至 2026-05-26） |

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-05-26 | 初版 |
| v1.1 | 2026-05-26 | 基于代码实际状态修正：Spec 弱化事实、OpenCode 委派机制、Tester 自动生成测试；重构亮点表达，使之更易理解 |
| v1.2 | 2026-05-26 | 突出 A2A 为亮点创新（四大创新）；修正臆造模型为 glm-4.7-fp8；移除错误价值主张"降低成本"；突出"设计文档驱动的超长超复杂系统开发"核心价值 |
| v1.3 | 2026-05-26 | 修正"现有工具=生成器"的错误对比；承认 harness（OpenCode 等）有工具调用能力，差异化在于 ASR 提供了 harness 缺少的"收敛大脑" |

---

## 目录

1. 问题定义与背景
2. 技术方案架构设计
3. 核心功能实现说明
4. 各功能模块使用说明
5. 创新说明
6. 落地部署方案

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
  Prompt → AI 调用工具 → 操作文件 → 跑测试 → 看报错 → 继续改 → ...（没有终止条件，靠人按 Ctrl+C）

ASR（harness 之上的收敛运行时）：
  Design → Builder 生成 → Tester 测试 → 退化？→ 回滚
                                 ↓ 通过
                            Analyzer 对比设计文档 → 有偏差？→ 定向修复
                                 ↓ 对齐
                            收敛退出 ✅
```

**核心价值**：

> **ASR 解决的是"从设计文档到完整系统的自动化开发"问题——这是现有 AI Coding 工具普遍无法解决的难题。**

当前 AI 编程工具（GitHub Copilot、Cursor、Claude Code 等）面对**超长超复杂系统**（多模块、多文件、有架构设计）时，几乎全部无法一次生成—因为它们没有"按设计文档开发"的能力，更没有"验证是否按设计完成"的机制。

ASR 的核心价值正是补上这一空白：
- **设计文档驱动的长系统开发**：输入 DESIGN.md，自动生成多模块、多文件的完整可运行代码工程——这正是目前只有头部互联网公司或模型厂商才具备的能力
- **复杂任务稳定收敛**：多轮迭代开发中，通过工程约束保证每轮产物不退化
- **企业私有化部署**：全文件化架构、零外部中间件依赖，支持离线环境和本地 LLM（如 glm-4.7-fp8），企业数据不出域

---

## 二、技术方案架构设计

### 2.1 总体架构

ASR 是一个三层架构的自治运行时，核心思路是**把 AI 当执行器，把人类当裁判**：

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户层                                    │
│   CLI 命令行（run / run-dag / init）                              │
│   输入：DESIGN.md（必需） + spec.yaml（可选）                      │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│                     控制层（ASR Runtime）                         │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              ASRController（收敛状态机）                   │    │
│  │                                                           │    │
│  │   REPAIRING ──→ TESTING ──→ 退化检测 ──→ ANALYZING      │    │
│  │       ↑            │           │              │            │    │
│  │       │            ↓           ↓              ↓            │    │
│  │       │      失败数 ↑?     回滚文件!      对齐? → CONVERGED│    │
│  │       │            │                         │            │    │
│  │       └────────────┴─── 修复指令 ←────────────┘            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─── A2C 协作流程（核心！三 Agent 独立进程、独立会话）────┐    │
│  │                                                          │    │
│  │  ┌─────────────┐  A2A   ┌─────────────┐  A2A  ┌───────┐│    │
│  │  │BuilderAgent │──────→│ TesterAgent │─────→│Analzr ││    │
│  │  │ 生成/修复    │ 事件  │ 测试生成+执行│ 事件 │语义裁决││    │
│  │  │ 带会话记忆   │      │ Sandbox隔离 │      │Sbx隔离││    │
│  │  └─────────────┘      └─────────────┘      └───────┘│    │
│  └──────────────────────────────────────────────────────────┘    │
          │                │                │
┌─────────▼────────────────▼────────────────▼─────────────────────┐
│                     执行层（OpenCode CLI）                        │
│                                                                  │
│  opencode run --format json --dir <project> [--session ID]      │
│  子进程调用，JSON流式输出，自动解析sessionID和token用量            │
│  支持任意 OpenAI 兼容模型（glm-4.7/Qwen3/GPT-4o/Claude）         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                     基础设施层                                    │
│  EventStore（事件审计）│ PatchEngine（diff修复）│ Logger+Tracker  │
│  全文件化存储 · FileLock原子写 · 可回放                           │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块职责

| 模块 | 文件 | 做什么 | 一句话 |
|------|------|--------|--------|
| **ASRController** | `controller/convergence.py` | 收敛状态机驱动、退化回滚、终止评估 | 大脑：决定什么时候修、什么时候停 |
| **BuilderAgent** | `agents/builder.py` | 代码生成/修复，带 OpenCode 会话延续 | 程序员：写代码改 Bug |
| **TesterAgent** | `agents/tester.py` | 自动生成测试 + pytest 执行，Sandbox 隔离 | 测试员：写测试跑测试 |
| **AnalyzerAgent** | `agents/analyzer.py` | 对比设计文档与代码，输出语义差距 | 审查员：查代码是否符合设计 |
| **OpenCode Backend** | `agents/opencode_backend.py` | 子进程调用 OpenCode CLI，解析 JSON 流 | 手：连接 AI 大脑和文件系统 |
| **EventStore** | `events/store.py` | 文件化事件存储、A2A 通信 | 黑匣子：记录一切，可回放 |
| **DAGExecutor** | `dag/executor.py` | 大任务拆解、并行执行收敛循环 | 并行调度器 |
| **PatchEngine** | `patch/diff.py` | unified diff 解析/应用/回滚 | 补丁工具箱 |
| **Config System** | `config/models.py` | Pydantic v2 配置模型，.env 加载 | 配置中心 |

### 2.3 ASR 与 OpenCode 的职责分工

这是理解 ASR 架构的关键——**ASR 不是另一个 LLM 调用框架，而是一个约束运行时**：

| 层 | 负责什么 | 不负责什么 |
|----|---------|----------|
| **ASR（约束层）** | 收敛循环、退化检测、语义裁决、会话管理、事件审计 | 不直接调用 LLM、不直接改文件 |
| **OpenCode（执行层）** | LLM 调用、代码生成/修改、Tool Calling、Context 管理 | 不知道收敛、不知道回滚、不知道裁决 |

### 2.4 系统运行阶段（Roadmap）

| 阶段 | 状态 | 核心能力 |
|------|------|---------|
| Phase 1: 单任务收敛 MVP | ✅ 已实现 | Builder+Tester+Analyzer 收敛循环 |
| Phase 2: 文件化 A2A 事件系统 | ✅ 已实现 | 20 种事件类型 + Inbox 轮询 + 事件回放 |
| Phase 3: Task DAG 并行 | ✅ 已实现 | 任务拆解 + 拓扑排序 + asyncio 并行 |
| Phase 4: Verification Mesh | 🔮 规划中 | SecurityAgent + PerformanceAgent + ArchitectureAgent |

---

## 三、核心功能实现说明

### 3.1 收敛循环：ASR 的心脏

ASR 的核心不是一个聊天循环，而是一个**有退出条件的工程状态机**：

```
每轮迭代：

  ① REPAIRING（修复阶段）
     首轮：Builder 读 DESIGN.md，从零生成代码
     后续：根据测试失败 + 语义分析反馈，定向修复
     → 修复前，Controller 自动快照所有 .py 文件（rollback 备份）

  ② TESTING（测试阶段）
     复制项目到 Sandbox → OpenCode 生成 pytest 测试 → 执行 pytest
     → 测试文件持久化回写 tests/（下次直接复用）

  ③ 退化检测（关键安全网）
     if 修复后失败数 > 修复前失败数:
         自动回滚所有文件到修复前状态
         删除修复中新增的 .py 文件

  ④ ANALYZING（语义裁决，测试通过后执行）
     对比 DESIGN.md 与代码实现
     输出 missing_features / logic_issues / constraint_violations
     → 全部为空 → CONVERGED（收敛成功！）
     → 有偏差 → 携带 findings 进入下一轮 REPAIRING
```

**核心代码（收敛主循环）**：

```python
# asr/controller/convergence.py — 核心循环
while iteration < self._config.convergence.max_iterations:
    # 1. 修复
    repair_events = await self._repairing_phase(task_id, prev_failures, prev_feedback)
    # 2. 测试
    test_events = await self._testing_phase(task_id)
    # 3. 退化检测 → 自动回滚
    if after_count > before_count and self._rollback_entries:
        for entry in reversed(self._rollback_entries):
            target.write_text(entry.original_content)  # 恢复文件！
    # 4. 测试通过 → 语义裁决
    if not test_failed:
        analysis_events = await self._analyzing_phase(task_id, test_events)
        if spec_aligned:
            return result  # ✅ 收敛成功
    # 5. 收集失败信息，下一轮定向修复
    prev_failures = [test failure details]
    prev_feedback = [analyzer findings]
```

### 3.2 三大亮点功能详解

#### 亮点一：双层裁决——AI 不能自己判自己及格

这是 ASR 最核心的创新。现有 AI Coding 工具的问题是：**AI 既写代码，又判断代码对不对**——就像让学生自己给自己判卷子。

ASR 的做法是：**两个独立的裁判，各判各的，都通过才算过**。

| 裁判 | 判什么 | 怎么判 | 通俗类比 |
|------|--------|--------|---------|
| **Tester（硬约束裁判）** | 代码能不能跑对 | 在隔离 Sandbox 里生成测试、跑 pytest | 理科考试：答案对就是对，错就是错 |
| **Analyzer（语义裁判）** | 代码是不是符合设计 | 对比 DESIGN.md 与代码，找遗漏和偏差 | 文科考试：有没有遗漏论点、偏不偏题 |

```
判定流程：

  Tester 说不通过 → 打回 Builder 重修（不管 Analyzer 说什么）
  Tester 说通过 → 再交 Analyzer 审
  Analyzer 说还有偏差 → 把偏差反馈给 Builder 定向修复
  Analyzer 说对齐了 → ✅ 收敛成功！
```

**为什么不能只用一个裁判？**
- 只用 Tester：代码能跑，但功能不全（修了个登录页，忘了注册页）
- 只用 Analyzer：逻辑对了，但代码有 Bug（看着像对的，一跑就崩）
- **两个都要过，才是真的过**

#### 亮点二：退化自动回滚——越修越坏时自动刹车

人类程序员都有这种经历：改了一个地方，结果另外三个地方坏了。AI 也会犯同样的错——而且更频繁，因为 AI 不知道自己改了什么。

ASR 的做法极其简单但有效：

```
每轮修复前：快照所有 .py 文件
每轮测试后：
  if 修复后失败数 > 修复前失败数:
      自动恢复所有文件到修复前状态
      删除修复中新增的非测试 .py 文件
```

**一句话：改坏了就撤回去，绝不让你越改越烂。**

代码实现（convergence.py L129-141）：
```python
if after_count > before_count and self._rollback_entries:
    snapshotted = {e.file_path for e in self._rollback_entries}
    for entry in reversed(self._rollback_entries):
        target = self._project_dir / entry.file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.original_content)  # 恢复原文件
    for py_file in self._project_dir.rglob("*.py"):
        if "test_" in py_file.name or "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(self._project_dir))
        if rel not in snapshotted:
            py_file.unlink(missing_ok=True)  # 删除新增文件
```

**为什么这很重要？** 没有退化检测，AI 会陷入"修一个坏三个"的恶性循环，Token 烧完也没产出。有了退化回滚，系统能保证**每轮至少不会比上一轮更差**——这是收敛的基础。

#### 亮点三：Bypass 检测——AI 想作弊？系统看得见

AI 在被反复要求"通过测试"时，会想出"聪明"的办法——直接跳过测试、硬编码返回值、在 except 里 pass。这不是 AI 在故意捣乱，而是它在寻找最短路径通过验证。

ASR 的 Bypass 检测自动识别这些行为：

```python
# asr/agents/builder.py — _compute_diff_summary()
bypass_detected = any(p in diff_text for p in [
    "except:",              # 空异常捕获（吞掉错误）
    "pass",                 # 占位符（假装实现了）
    "if DEBUG:",            # 调试开关绕过
    "return expected",      # 硬编码期望返回值
    "mock(",                # 用 mock 替代真实实现
    "@pytest.mark.skip",   # 直接跳过测试
])
```

**一句话：AI 想偷懒绕过测试？系统一看便知，风险分自动 +25。**

### 3.3 OpenCode 委派执行机制

ASR 的所有 Agent 不直接调用 LLM API，而是通过 **OpenCode CLI** 子进程委派执行：

```
BuilderAgent ──→ opencode run --dir <project> --session <id> --continue <prompt>
TesterAgent  ──→ opencode run --dir <sandbox> <prompt>  （无状态，每次新建会话）
AnalyzerAgent──→ opencode run --dir <sandbox> <prompt>  （无状态，每次新建会话）
```

**关键设计决策**：

| Agent | 会话管理 | 原因 |
|-------|---------|------|
| Builder | **有状态**，跨迭代保持 `session_id`，用 `--continue` 延续 | Builder 需要"记住"之前的修改历史和项目状态 |
| Tester | **无状态**，每轮新建会话 | 防止错误污染，保证每轮测试从干净状态出发 |
| Analyzer | **无状态**，每轮新建会话 | 防止分析偏差累积，保证每轮独立判断 |

**Token 追踪**：从 OpenCode JSON 输出中解析 `step_finish` 事件，实时追踪每个 Agent 的 prompt/completion/total token 消耗，写入 `.runtime/logs/llm.jsonl`。

### 3.4 Sandbox 隔离机制

Tester 和 Analyzer 都在 `.asr_sandbox/` 中隔离执行：

```python
# asr/agents/tester.py
sandbox = self._project_dir / ".asr_sandbox" / "tester"
# 1. 复制项目文件到 Sandbox（排除 __pycache__ / .git / .asr_sandbox）
# 2. 在 Sandbox 中让 OpenCode 生成测试 + 执行 pytest
# 3. 将生成的测试文件回写到项目 tests/ 目录
# 4. 清理 Sandbox
```

**意义**：
- OpenCode 可能在 Sandbox 中修改任何文件，隔离确保不影响项目
- 生成的测试文件会回写，后续迭代直接复用
- Analyzer 同理，防止 OpenCode 在分析时修改项目代码

### 3.5 设计文档驱动的开发模式

ASR 实际的输入是 **DESIGN.md**（必需），不是 spec.yaml（可选）：

```python
# asr/runtime.py
async def run(self, project_dir, spec_path=None, ...):
    if spec_path and spec_path.exists():
        spec = Specification(**yaml.safe_load(f))  # 有 spec 就用 spec
    else:
        spec = Specification(goal=self._design_title(project_dir))  # 否则读 DESIGN.md 标题
```

**DESIGN.md 就是最高优先级的"需求文档"**：
- BuilderAgent 的 prompt 模板：`"根据设计文档DESIGN.md完成开发与自动化测试"`
- TesterAgent 的 prompt 模板：`"读取 DESIGN.md 了解系统设计 → 生成 pytest 测试"`
- AnalyzerAgent 的 prompt 模板：`"读取 DESIGN.md 和所有 .py 代码文件 → 对比设计文档与实现代码"`

### 3.6 本地化 A2A 事件系统

ASR 采用**文件化 A2A 协议**，不引入 Kafka/NATS 等分布式中间件：

- **20 种事件类型**：覆盖任务创建、代码生成、测试、补丁、分析、收敛等完整生命周期
- **原子写入**：FileLock + tmp→rename 模式，保证并发安全
- **两种 A2A 模式**：
  - 直接调用模式（默认）：Controller 直接调用 `agent.process(event)`
  - 解耦模式（`--decoupled`）：AgentRunner 异步轮询 inbox/ 目录，支持独立进程部署
- **事件回放**：所有事件存储在 `.runtime/events/`，可任意时刻回放重建系统状态

### 3.7 Task DAG 并行执行

针对大型任务，ASR 支持将任务拆解为 DAG 并行执行：

```python
# asr/dag/executor.py
while not dag.all_done():
    ready = dag.get_ready_nodes()        # 获取依赖已满足的节点
    await asyncio.gather(                 # 并行执行所有就绪节点
        *(self._run_node(dag, n, spec) for n in ready)
    )
```

- **两种拆解策略**：基于 Spec.features 的特征驱动 / 基于测试失败的修复驱动
- **文件冲突解决**：共享文件的节点自动建立隐式依赖，避免并发写入冲突

---

## 四、各功能模块使用说明

### 4.1 环境准备

**系统要求**：
- Python 3.10+（建议 3.11）
- OpenCode CLI（需提前安装并配置 LLM 后端）
- git（用于 diff 提取变更）

**依赖安装**：
```bash
cd /path/to/asr
pip install -r requirements.txt
# 主要依赖：click, pydantic>=2.0, pyyaml, filelock
```

**配置 LLM 后端**（`.env` 文件）：
```bash
FEASIBILITY_LLM_MODEL=glm-4.7-fp8
FEASIBILITY_LLM_API_BASE=http://192.168.1.12:8000/v1
FEASIBILITY_LLM_API_KEY=sk-your-key
FEASIBILITY_LLM_CONTEXT=200000
ASR_OPENCODE_TIMEOUT=7200
```

### 4.2 项目初始化

```bash
python -m asr.cli.main init --project ./my_project
```

自动创建目录结构：
```
my_project/
├── asr_config.yaml        # ASR 配置文件（自动生成）
└── .runtime/              # 运行时数据目录
    ├── events/            # 事件 JSON 文件
    ├── inbox/             # A2A 消息 inbox（builder/tester/analyzer）
    ├── logs/              # asr.log + llm.jsonl
    ├── patches/           # Patch 文件存储
    ├── diffs/
    ├── state/
    └── tasks/
```

**项目必需文件**：
```
my_project/
├── DESIGN.md              # 设计文档（必需！Agent 的核心输入）
└── tests/                 # 测试文件（可空，TesterAgent 自动生成）
```

### 4.3 执行收敛（run 命令）

**基本使用**（最简命令，只需指定项目目录）：
```bash
python -m asr.cli.main run --project ./my_project
```

**完整参数**：
```bash
python -m asr.cli.main run \
  --project /path/to/project \    # 项目目录（必需）
  --spec /path/to/spec.yaml \     # 结构化 Spec（可选，默认读 DESIGN.md）
  --max-iterations 10 \           # 最大迭代次数（默认 5）
  --decoupled \                    # 解耦 A2A 模式
  --verbose                        # 详细日志输出
```

**实时进度输出**：
```
ASR Runtime [direct]
Project: /path/to/project
Spec: (from DESIGN.md)
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

### 4.4 DAG 模式执行

```bash
python -m asr.cli.main run-dag \
  --project /path/to/project \
  --spec /path/to/spec.yaml   # DAG 模式需要 spec.yaml 定义 features
```

### 4.5 一键启动脚本

```bash
./start_asr.sh
```

脚本自动执行：清理上次运行数据 → 创建开发工作区 → 复制 DESIGN.md → 启动 ASR。

### 4.6 日志与可观测性

| 日志文件 | 位置 | 内容 |
|---------|------|------|
| 收敛日志 | `.runtime/logs/asr.log` | 每轮迭代的阶段、错误数、耗时 |
| LLM 追踪 | `.runtime/logs/llm.jsonl` | 每个 Agent 的 Token 消耗明细 |
| 事件审计 | `.runtime/events/*.json` | 完整事件流，可任意回放 |
| 运行状态 | `.runtime/state/*.json` | 收敛/卡住终态 |

---

## 五、创新说明

### 5.1 核心价值：从设计文档到完整系统的自动化开发

> **这是 ASR 最根本的差异化价值，也是其他 AI Coding 工具普遍缺失的能力。**

当前 AI 编程工具的能力边界：

| 能力层级 | 典型工具 | 能做什么 | 做不到什么 |
|---------|---------|---------|----------|
| **L1 代码补全** | GitHub Copilot | 写一个函数、补一段逻辑 | 不知道整个系统该长什么样 |
| **L2 单任务对话** | ChatGPT、Claude | 聊天式改一个文件 | 多文件联动修改、跑测试验证 |
| **L3 Agent 模式** | Cursor Agent、Claude Code | 自动探索项目、改多个文件 | 没有收敛机制、不知道什么时候做完、没有退化防护 |
| **L4 设计驱动开发** | **ASR（本方案）** | 读设计文档→生成多模块系统→自动测试→语义验证→收敛 | — |

**L4 为什么难？** 因为它同时需要四个能力：
1. 能读懂并遵循设计文档（不是随意生成）
2. 多 Agent 协作开发（不是单 Agent 猜测）
3. 自动验证是否按设计完成（不是 AI 自己说"好了"）
4. 退化防护（不是越改越差）

目前只有头部互联网或模型厂商（如 Devin）具备类似 L4 能力，且均为 SaaS 云服务，**企业私有化部署方案几乎为零**。ASR 正是填补这一空白的方案。

### 5.2 四大核心创新（通俗版）

基于上述核心价值，ASR 有四项关键创新：

#### 创新一：A2A 多智能体协作——让 AI 团队开发成为可能

**问题**：单个 AI Agent 无法同时写代码、跑测试、审查质量——就像一个人不能同时当程序员、测试员和审查员。现有 AI Coding 工具要么只用一个 Agent（Cursor Agent），要么用串行 Pipeline 但没有真正的协作（Devin）。

**ASR 的做法**：三个独立 Agent，通过文件化 A2A 事件协议协作：

```
Builder（程序员）──A2A事件──→ Tester（测试员）──A2A事件──→ Analyzer（审查员）
   ↑                              │                           │
   │     修复指令（test_failures）  │    审查反馈（findings）    │
   └──────────────────────────────┴───────────────────────────┘
```

**A2A 的关键设计**：

| 设计决策 | 为什么 |
|---------|-------|
| 三个 Agent 独立进程、独立 OpenCode 会话 | 防止 Agent 间上下文污染 |
| Builder 有状态延续（session_id），Tester/Analyzer 无状态 | Builder 需要"记住"改了什么；Tester/Analyzer 每轮独立判断 |
| A2A 事件全部文件化存储（`.runtime/events/`） | 可回放、可审计、可调试 |
| 支持 `--decoupled` 解耦模式（AgentRunner 轮询 inbox/） | Agent 可部署为独立进程，实现真正的分布式协作 |

**对比现有工具**：

| | 单 Agent 工具 | Pipeline 工具 | **ASR A2A** |
|--|-------------|-------------|------------|
| Agent 数量 | 1 个 | 多个（串行） | 3 个（协作+独立） |
| Agent 间通信 | 无 | 函数调用 | **文件化事件协议** |
| 会话隔离 | 无 | 无 | **独立会话、独立状态** |
| 可审计性 | 无 | 无 | **全事件回放** |
| 分布式部署 | 不支持 | 不支持 | **--decoupled 模式** |

#### 创新二：双层裁决——AI 不能自己给自己打分

**问题**：现有 AI Coding 工具，AI 既写代码又判断对不对——学生自己给自己判卷子，能不及格吗？

**ASR 的做法**：设两个独立裁判：
1. **Tester（硬裁判）**：在隔离环境里跑 pytest，代码要么跑通要么跑不通
2. **Analyzer（软裁判）**：对比设计文档和代码，找功能遗漏和逻辑偏差

两个裁判都通过，才算真正及格。而且——**裁判不是同一个 AI**，而是独立进程、独立会话、独立状态，互不干扰。

**对比**：

| | 现有工具 | ASR |
|--|---------|-----|
| 验证方式 | AI 自己说"看起来没问题" | pytest 客观结果 + 语义分析独立裁决 |
| 功能遗漏 | 发现不了 | Analyzer 专门检查"设计文档要求但代码没实现的" |
| 修 A 坏 B | 不知道 | 退化检测自动回滚 |

#### 创新三：退化自动回滚——改坏了自动撤回

**问题**：AI 修 Bug 的典型模式是"修了 A，结果 B 和 C 坏了"，然后越修越多，越改越烂。

**ASR 的做法**：每轮修复前自动快照所有文件。修完后如果失败数反而增加了——自动恢复到修复前状态，当作这轮没发生过。

**一句话总结：绝不允许"越改越差"，每轮至少不会比上一轮更坏。**

这听起来简单，但**没有其他 AI Coding 工具做这件事**。因为现有工具根本没有"修复前后对比"的概念——它们不知道上一轮有几个测试失败，也不知道这一轮修完后是变好还是变差。

#### 创新四：Bypass 检测——AI 作弊自动发现

**问题**：AI 被反复要求"通过测试"时，会"聪明地"选择最短路径——跳过测试、硬编码返回值、空异常捕获。这不是 AI 故意捣乱，而是在奖励信号下找到的最优解。

**ASR 的做法**：自动检测 diff 中的 bypass 模式（`except: pass`、`return expected`、`@pytest.mark.skip` 等），发现后风险分自动 +25，系统可据此决定是否采纳这次修复。

**一句话总结：AI 想偷懒绕过测试？系统自动识别并标记。**

### 5.3 与现有方案的系统对比

| 对比维度 | GitHub Copilot | Claude Code | Cursor Agent | **ASR** |
|---------|---------------|-------------|-------------|---------|
| **设计文档驱动开发** | ❌ 不支持 | ❌ 不支持 | ❌ 不支持 | **✅ DESIGN.md → 完整系统** |
| **多智能体协作** | 单 Agent | 单 Agent | 单 Agent | **A2A 三 Agent 协作** |
| **验证方式** | 无（用户自验） | LLM 自评 | LLM 自评 | **双层外部验证** |
| **修复策略** | 手动重写 | 全量重新生成 | 全量重新生成 | **unified diff 局部修复** |
| **终止条件** | 用户手动停 | 用户手动停 | 用户手动停 | **三重终止：通过+对齐/最大迭代/退化回滚** |
| **退化防护** | 无 | 无 | 无 | **自动检测+回滚** |
| **作弊检测** | 无 | 无 | 无 | **Bypass 模式识别** |
| **会话管理** | 无状态 | 单会话 | 单会话 | **Builder 有状态延续，Tester/Analyzer 无状态隔离** |
| **可审计性** | 无 | 无 | 无 | **全事件文件化存储、可回放** |
| **私有化部署** | SaaS | SaaS | SaaS/本地 | **全文件化架构，零中间件依赖，支持离线** |

### 5.4 概念映射创新：从 Prompt Engineering 到 Runtime Engineering

ASR 将 AI 软件工程的范式从"调 Prompt"转向"建约束"：

| AI 概念 | 传统做法 | ASR 对应 | 区别 |
|---------|---------|---------|------|
| 需求输入 | 口头描述，祈祷输出 | **DESIGN.md 驱动** | 可验证、可追踪，支持超长系统 |
| Agent 协作 | 单 Agent 干所有事 | **A2A 三 Agent 事件协作** | 职责分离，防止自我认证，可审计 |
| Chat | 聊到满意为止 | 收敛循环 | 有退出条件 |
| Context | 塞进更多上下文 | 外部化到文件和事件流 | 不依赖 LLM 记忆 |
| Retry | 换个说法再试 | 差异驱动的定向修复 | 修哪知道，不乱改 |
| Reflection | AI 自我反思 | 双层外部裁决 | 外部强制，非自我感觉 |

### 5.5 商业价值

#### 价值一：填补"设计文档→完整系统"的能力空白

这是 ASR 最大的商业价值。当前 AI 编程市场的分层现状：

| 市场层级 | 能力 | 代表产品 | ASR 对应 |
|---------|------|---------|---------|
| L1 代码补全 | 写函数、补逻辑 | Copilot | — |
| L2 对话式开发 | 单文件修改+对话 | ChatGPT | — |
| L3 Agent 自动化 | 多文件探索+修改 | Claude Code、Cursor | — |
| **L4 设计驱动开发** | **读设计文档→生成完整系统→自动收敛** | **仅 Devin（SaaS）** | **✅ ASR** |

关键差距在于：
- **L1-L3 工具只能做"小任务"**：单函数、单文件、局部修改，无法处理多模块、多文件、有架构设计的系统级开发
- **L4 能力极度稀缺**：全球只有 Devin 等极少数产品具备类似能力，且全部是 SaaS 云服务
- **企业私有化部署几乎为零**：没有面向企业的"设计文档驱动的系统级开发"私有化方案

ASR 正是填补"L4 私有化部署"空白的方案——在本地 LLM（如 glm-4.7-fp8）上，从一个设计文档自动开发出完整可运行的代码工程。

#### 价值二：企业私有化部署

- **全文件化架构**：零外部中间件依赖（无 Kafka/NATS/Redis），支持离线环境
- **本地 LLM 兼容**：实际运行于 glm-4.7-fp8（200K 上下文），企业数据不出域
- **可审计可回放**：所有 A2A 事件文件化存储，满足企业合规要求

#### 价值三：Bug 修复自动化

基于实测数据，AI 辅助开发中 **47.2% 的任务是 Bug 修复**（见附录 B）。ASR 的自动修复-验证-收敛循环，直接命中最高频开发痛点。

> ⚠️ **关于 Token 成本**：ASR 的价值不在于降低 Token 消耗——多轮迭代收敛确实需要消耗大量 Token。ASR 的真正价值在于：**让 AI 能够完成单次对话无法完成的复杂系统级开发任务**——这是"能不能做到"的问题，不是"花多少钱"的问题。

---

## 六、落地部署方案

### 6.1 部署方式

**方式一：本地 CLI 直接运行（推荐开发测试）**
```bash
git clone <repo>
cd asr
pip install -r requirements.txt
# 配置 .env（设置 LLM 后端地址）
python -m asr.cli.main run --project ./my_project --max-iterations 10
```

**方式二：Shell 脚本一键启动**
```bash
./start_asr.sh  # 封装了环境检查、目录清理和参数配置
```

**方式三：集成到 CI/CD 流水线**
```yaml
# .github/workflows/asr.yml 示例
- name: ASR 自动修复
  run: |
    python -m asr.cli.main run \
      --project . \
      --max-iterations 5
```

### 6.2 依赖环境

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | ≥ 3.10 | 核心运行时 |
| OpenCode CLI | 最新版 | LLM 调用层（必需） |
| git | ≥ 2.x | diff 提取变更 |
| pytest | ≥ 7.0 | 测试执行 |
| pydantic | ≥ 2.0 | 数据模型 |
| click | ≥ 8.0 | CLI 界面 |
| pyyaml | ≥ 6.0 | 配置/YAML 解析 |
| filelock | ≥ 3.0 | 原子写入 |

**无需**：数据库、消息队列、Docker、云服务

### 6.3 模型兼容性

ASR 通过 OpenCode CLI 调用 LLM，与具体模型完全解耦：

| 模型 | 状态 | 说明 |
|------|------|------|
| **glm-4.7-fp8** | ✅ **实际使用** | 主要开发与测试模型，200K 上下文，本地部署 |
| qwen3-next-80b-a3b-instruct | ✅ 已配置 | .env 中已配置，可作为备选 |
| 其他 OpenAI 兼容接口 | ✅ 兼容 | 通过 .env 配置 FEASIBILITY_LLM_API_BASE 即可 |

**模型选择建议**：
- 核心要求是**长上下文能力**（≥ 100K），因为 Builder 需要读 DESIGN.md + 已有代码
- Builder 任务（代码生成/修复）建议使用参数量较大的模型（≥ 14B）
- Tester 和 Analyzer 任务对模型要求相对较低，7B 级别模型即可
- 生产环境建议设置 `ASR_OPENCODE_TIMEOUT=7200`（2小时），避免复杂任务超时

### 6.4 运维注意事项

1. **磁盘空间**：每次运行在 `.runtime/` 下写入事件、日志文件，建议定期清理（保留最近 10 次）
2. **并发运行**：同一项目目录不支持同时运行多个 ASR 实例；DAG 模式内部的子任务并行是安全的
3. **回滚数据**：Controller 每轮 REPAIRING 前自动创建快照（内存中）。若进程中断，可通过 `.runtime/events/` 事件流回放分析中断状态
4. **Token 预算**：通过 `--max-iterations` 和 `convergence.max_iterations` 控制最大迭代次数，监控 `.runtime/logs/llm.jsonl` 追踪实际消耗
5. **Sandbox 清理**：Tester/Analyzer 执行后自动清理 `.asr_sandbox/`，若进程中断可手动删除

---

## 附录

### A. 系统文件结构

```
asr/
├── asr/
│   ├── cli/
│   │   └── main.py              # CLI 入口（Click）
│   ├── controller/
│   │   └── convergence.py       # 收敛状态机（核心）
│   ├── agents/
│   │   ├── base.py              # BaseAgent 抽象
│   │   ├── builder.py           # BuilderAgent（有状态会话延续）
│   │   ├── tester.py            # TesterAgent（Sandbox + 测试生成）
│   │   ├── analyzer.py          # AnalyzerAgent（Sandbox + YAML 分析）
│   │   ├── runner.py            # AgentRunner（解耦轮询）+ AgentOrchestrator
│   │   ├── opencode_backend.py  # OpenCode CLI 子进程调用
│   │   └── llm_tracker.py       # Token 追踪
│   ├── dag/
│   │   ├── models.py            # TaskNode / TaskDAG / DAGResult
│   │   ├── decomposer.py        # 任务拆解（特征/失败驱动）
│   │   └── executor.py          # 并行执行
│   ├── events/
│   │   ├── models.py            # 20 种事件类型（Pydantic）
│   │   └── store.py             # EventStore（文件化 + FileLock）
│   ├── patch/
│   │   └── diff.py              # PatchEngine（unified diff）
│   ├── spec/
│   │   └── models.py            # Specification 模型
│   ├── config/
│   │   ├── models.py            # ASRConfig（Pydantic v2）
│   │   └── loader.py            # .env 加载 + 默认配置
│   ├── logger.py                # ASRLogger
│   └── runtime.py               # ASRRuntime（编排入口）
├── tests/                        # 单元测试（10 个测试文件）
├── demo_dev/                     # Demo 工程（可研报告编译器）
├── requirements.txt
└── start_asr.sh                  # 一键启动脚本
```

### B. 开发任务统计背景数据

基于 WorkBuddy 工具统计的 36 个开发任务（2026-04-14 至 04-23）分布：

| 任务类型 | 数量 | 占比 |
|---------|------|------|
| 发现 Bug | 17 | 47.2% |
| 新需求 | 7 | 19.4% |
| Review | 6 | 16.7% |
| 改需求 | 5 | 13.9% |
| 需求未实现 | 2 | 5.6% |
| 其他 | 2 | 5.6% |

**数据洞察**：Bug 修复占据将近一半的开发时间（47.2%）。ASR 的自动化修复-验证-收敛循环，正是针对这一最高频开发痛点的精准解决方案。

### C. 核心收敛终止条件

| 终止条件 | 触发机制 | 实现状态 |
|---------|---------|---------|
| 测试通过 + 语义对齐 | `passed_all AND spec_aligned` → CONVERGED | ✅ 已实现 |
| 最大迭代次数 | `iteration >= max_iterations` → STUCK | ✅ 已实现（默认 5 轮） |
| 退化自动回滚 | `after_count > before_count` → 恢复文件 | ✅ 已实现 |
| Diff 稳定检测 | 相同 patch 连续出现 N 次 → STUCK | 🔮 配置已预留，待接入 |
| Patch 震荡检测 | 两个 patch 交替出现 → STUCK | 🔮 配置已预留，待接入 |

### D. 实际 Demo 运行效果

ASR 已通过可研报告编译器 Demo（demo_dev/）完成端到端验证：

- **输入**：47KB 设计文档（DESIGN.md，可研报告编译器 v4.3 设计方案）
- **输出**：完整可运行的代码工程（compiler/ 目录，含 DAG/Pack/Schema/Agent/Skills/Renderer 等模块）+ 8 个测试文件
- **迭代**：10 轮收敛循环，Builder 生成代码 → Tester 生成测试 → Analyzer 检查对齐

---

*本报告对应系统版本：ASR v1.1 | 文档同步日期：2026-05-26*
