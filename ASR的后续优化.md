# ASR 的后续优化：用控制论提升 AI Software Runtime

听评论提到“控制论”后，我重新查阅并分析了 ASR（AI Software Runtime）的系统结构，发现一个非常关键的判断：

> **ASR 本质上已经是控制论在 AI 软件工程中的一种实现。**

ASR 当前的核心闭环是：

```text
Builder 生成 / 修复代码
        ↓
Tester 执行测试验证
        ↓
Analyzer 对照 DESIGN.md 做语义裁决
        ↓
Controller 汇总反馈并决定继续修复、回滚、收敛或停止
        ↓
Builder 进入下一轮修复
```

这和控制论中的经典闭环结构高度一致：

```text
目标 → 控制器 → 执行器 → 被控对象 → 传感器 → 反馈 → 控制器
```

在 ASR 中，对应关系如下：

| 控制论概念 | ASR 中的对应物 |
|---|---|
| 目标值 / Reference | `DESIGN.md`、结构化 Spec、验收标准 |
| 控制器 / Controller | `ASRController` |
| 执行器 / Actuator | `BuilderAgent` |
| 被控对象 / Plant | 正在生成或修复的软件工程代码 |
| 传感器 / Sensor | `TesterAgent`、`AnalyzerAgent` |
| 反馈 / Feedback | 测试失败、规格偏差、Analyzer findings、运行错误 |
| 状态记忆 / Memory | `EventStore`、`.runtime/events`、patch history |
| 控制动作 / Control Action | 生成 patch、回滚、继续迭代、终止 |
| 收敛目标 / Convergence Goal | 测试全部通过，并且实现与规格一致 |

因此，ASR 并不是一个简单的 Agent Workflow，也不是单纯的 Prompt Engineering，而是一个：

> **面向 AI 软件生成的闭环控制运行时。**

---

## 一、从第一性原理看 ASR 为什么天然适合控制论

软件开发的本质不是“写代码”，而是不断减少“需求”和“实现”之间的差异。

```text
软件开发 = 需求与实现之间的持续差异消除
```

也就是：

```text
需求 → 实现 → 验证 → 发现偏差 → 修复偏差 → 再验证 → 收敛
```

这正是控制论中的闭环反馈机制。

对于 AI 编程系统来说，LLM 本身并不是可靠的确定性执行器。它会出现：

- 长任务漂移；
- 局部修复破坏旧功能；
- 测试通过但需求未完整实现；
- 语义理解偏差；
- 上下文污染；
- 输出不稳定；
- 自信但错误的判断。

所以，如果只依赖“模型一次性生成”，系统是不稳定的。

ASR 的核心价值就在于：

```text
不相信单次生成，而相信闭环收敛。
```

也就是说：

```text
弱模型 + 强约束 + 外部反馈 + 持续修复 = 稳定软件生成系统
```

从控制论角度看，ASR 的目标不是让 Builder 一次生成正确代码，而是让整个系统在反馈控制下逐步趋近正确实现。

---

## 二、当前 ASR 已经具备的控制论能力

### 1. 闭环反馈

ASR 当前已经形成了完整闭环：

```text
Generate → Verify → Diff → Repair → Re-Verify → Converge
```

其中：

- Builder 负责生成和修复；
- Tester 负责硬约束验证；
- Analyzer 负责语义规格验证；
- Controller 负责根据反馈做控制决策；
- EventStore 负责记录系统状态和事件轨迹。

这已经具备控制系统的基本形态。

### 2. 双层传感器

ASR 当前有两个核心反馈源：

#### TesterAgent：硬反馈传感器

负责回答：

```text
代码能不能运行？
测试是否通过？
有没有编译错误或运行错误？
```

优点是确定性强、可重复、信号清晰。

缺点是只能覆盖测试写到的部分。

#### AnalyzerAgent：语义反馈传感器

负责回答：

```text
代码是否符合 DESIGN.md？
是否遗漏功能？
是否违反设计约束？
是否存在逻辑偏差？
```

优点是可以发现测试之外的需求偏差。

缺点是它本身也是 LLM 驱动，反馈存在噪声。

因此，ASR 当前已经是一个“双传感器闭环控制系统”。

### 3. 状态外部化

ASR 不依赖 LLM context 作为系统真实状态，而是通过 EventStore 记录事件。

这非常关键。

因为 LLM context 会：

- 遗忘；
- 污染；
- 漂移；
- 被历史错误误导。

而控制系统必须有稳定、可审计、可回放的外部状态。

因此，ASR 的事件系统可以进一步升级为：

```text
状态估计器 / State Estimator
```

也就是通过事件流判断：

- 当前系统是否在收敛；
- 错误数量是否下降；
- patch 是否反复震荡；
- Builder 是否进入无效修复；
- Analyzer 是否反复报告同类问题；
- 系统是否应该继续、回滚或停止。

### 4. 回滚机制

ASR 已有 patch 退化后的回滚能力。

这对应控制论中的安全保护机制：当控制动作导致系统输出恶化时，撤销该动作，避免系统进一步发散。

在 AI 编程场景中，这非常重要。

因为 Builder 可能为了修一个测试，改坏十个已经通过的功能。

---

## 三、当前 ASR 还缺少的控制论能力

虽然 ASR 已经是控制论式系统，但目前更多是“工程闭环”，还没有完全升级为“显式控制系统”。

后续优化的核心方向是：

> **把隐式反馈变成显式误差信号，把经验规则变成可观测、可调参、可分析的控制策略。**

当前主要缺口如下。

---

### 1. 缺少统一的误差函数

现在 ASR 可以知道：

- 测试失败了几个；
- Analyzer 发现了什么问题；
- patch 是否应用成功；
- 是否达到最大迭代次数。

但这些信号还没有统一成一个整体误差函数。

后续可以定义：

```text
Error Score =
  α * 测试失败数
+ β * 编译错误数
+ γ * 缺失功能数
+ δ * 逻辑偏差数
+ ε * 约束违规数
+ ζ * 高严重问题数
+ η * patch 退化风险
+ θ * token / 时间成本
```

这样每一轮都可以判断：

```text
本轮是否比上一轮更接近目标？
```

而不是只判断：

```text
是否已经完全通过？
```

这会让 ASR 从“结果型判断”升级为“过程型控制”。

---

### 2. 缺少收敛趋势判断

一个控制系统不仅要知道当前误差，还要知道误差变化趋势。

ASR 后续可以记录：

```text
error_score_t
error_score_t-1
error_delta = error_score_t - error_score_t-1
```

根据变化趋势判断：

| 趋势 | 含义 | 控制动作 |
|---|---|---|
| 误差下降 | 正在收敛 | 继续当前策略 |
| 误差不变 | 停滞 | 缩小修复范围或重新分析 |
| 误差上升 | 退化 | 回滚或切换策略 |
| 误差来回波动 | 振荡 | 触发 stuck 或改变控制模式 |

这可以避免 ASR 陷入“看起来一直在修，实际上没有进展”的状态。

---

### 3. 缺少 patch 振荡检测

AI 修复系统很容易出现振荡：

```text
第 3 轮：改成 A
第 4 轮：改成 B
第 5 轮：又改回 A
第 6 轮：又改回 B
```

或者：

```text
同一个 patch 被反复生成，但测试和 Analyzer 结果没有改善
```

这在控制论中类似极限环或震荡。

ASR 后续应该对 patch 做 fingerprint：

```text
patch_fingerprint = hash(修改文件 + diff hunk + 修改意图)
```

并检测：

- 同一 patch 连续出现；
- A/B patch 交替出现；
- patch 相似度很高但误差不下降；
- 同一测试失败被反复修复但一直失败。

一旦检测到振荡，就不应该继续普通 repair，而应该切换策略：

- 重新读取 DESIGN.md；
- 要求 Analyzer 做根因分析；
- 缩小 patch 范围；
- 回滚到上一个稳定点；
- 标记为 STUCK；
- 请求人工介入。

---

### 4. 缺少控制增益

控制论中，控制器需要控制输出强度。

对应 ASR，就是 Builder 每轮修复的力度。

修复力度太小：

```text
系统收敛很慢，甚至停滞。
```

修复力度太大：

```text
容易改坏已通过功能，引发退化。
```

后续可以引入 patch 限幅：

```text
每轮最多修改多少文件？
每轮最多修改多少行？
是否允许重写整个模块？
是否只允许修改与失败测试相关的文件？
是否允许删除已有代码？
```

根据不同阶段动态调整修复强度：

| 阶段 | 修复策略 |
|---|---|
| 初始生成 | 允许大范围创建文件 |
| 编译错误 | 最小修复，先恢复可运行 |
| 少量测试失败 | 局部 patch |
| 大量测试失败 | 模块级重构或回滚 |
| 语义缺失 | 补功能，而不是只修测试 |
| 振荡状态 | 降低 patch 范围，重新分析 |

这会让 Builder 从“自由生成器”变成“受控执行器”。

---

### 5. Analyzer 需要从文本反馈升级为结构化传感器

Analyzer 当前的核心价值很高，但它本身也是 LLM 驱动，因此反馈有噪声。

后续 Analyzer 的输出不应该只是自然语言 findings，而应该结构化：

```yaml
findings:
  - category: MISSING
    severity: HIGH
    confidence: 0.92
    message: 用户认证模块未实现
    evidence:
      - DESIGN.md 第 3 节要求 OAuth2 登录
      - src/auth.py 不存在
    affected_files:
      - src/auth.py
    blocking: true
```

这样 Controller 就可以做更精确的融合：

- 高严重 + 高置信 → 必须修；
- 高严重 + 低置信 → 需要二次验证；
- 低严重 + 低置信 → 不阻塞收敛；
- 多轮重复出现 → 提升优先级；
- 与测试失败相关 → 提升优先级。

这会显著降低 Analyzer 噪声对 Builder 的干扰。

---

### 6. 需要多传感器融合，而不是简单堆 Agent

ASR 后续规划中的 Verification Mesh 非常适合控制论升级。

但要注意，不能只是增加更多 Agent。

正确方式是让每个 Agent 成为一个明确维度的传感器：

| Agent | 反馈维度 |
|---|---|
| TesterAgent | 正确性、可运行性 |
| AnalyzerAgent | 需求一致性 |
| SecurityAgent | 安全风险 |
| PerformanceAgent | 性能风险 |
| ArchitectureAgent | 架构合规 |
| MaintainabilityAgent | 可维护性 |

每个 Agent 输出结构化 verdict，然后 Controller 做融合：

```text
final_error =
  w_test * test_error
+ w_spec * spec_error
+ w_security * security_error
+ w_perf * performance_error
+ w_arch * architecture_error
+ w_maintainability * maintainability_error
```

这样 ASR 才会从“测试通过型系统”升级为“多维质量收敛系统”。

---

## 四、建议的后续架构升级

### 1. 引入 ConvergenceMetrics

每轮迭代后生成统一指标：

```python
ConvergenceMetrics:
    iteration: int
    test_failed_count: int
    test_error_count: int
    missing_feature_count: int
    logic_issue_count: int
    constraint_violation_count: int
    high_severity_count: int
    patch_count: int
    changed_file_count: int
    changed_line_count: int
    rollback_count: int
    repeated_failure_count: int
    oscillation_score: float
    error_score: float
```

每轮都记录：

```text
当前误差是多少？
相比上一轮是改善、停滞还是退化？
是否存在振荡？
是否应该切换控制策略？
```

---

### 2. 引入 RepairMode

不同失败形态应该触发不同修复模式：

```python
RepairMode:
    INITIAL_GENERATION
    COMPILE_FIX
    TEST_FIX
    SPEC_COMPLETION
    REGRESSION_RECOVERY
    OSCILLATION_BREAK
    FINAL_VERIFICATION
```

对应策略：

| RepairMode | 策略 |
|---|---|
| INITIAL_GENERATION | 根据 DESIGN.md 创建完整项目 |
| COMPILE_FIX | 最小修改，先让项目可运行 |
| TEST_FIX | 针对失败测试局部修复 |
| SPEC_COMPLETION | 重新对照 DESIGN.md 补齐缺失功能 |
| REGRESSION_RECOVERY | 回滚或恢复旧功能 |
| OSCILLATION_BREAK | 停止普通修复，做根因分析 |
| FINAL_VERIFICATION | 做收敛确认，不做大改 |

这样 ASR 的修复策略会更加稳定。

---

### 3. 引入 Patch 限幅

对 Builder 的输出做约束：

```text
max_files_per_patch
max_lines_changed_per_patch
max_deleted_lines_per_patch
allow_large_patch_only_in_initial_generation
require_evidence_for_large_patch
```

避免 Builder 过度修改导致退化。

---

### 4. 引入振荡检测

记录 patch fingerprint 和失败模式 fingerprint：

```text
patch_history = [A, B, A, B]
failure_history = [X, Y, X, Y]
```

检测：

- 同 patch 重复；
- A/B 交替；
- 同测试失败反复出现；
- 同 Analyzer finding 反复出现；
- error_score 长期不下降。

触发：

```text
STUCK
OSCILLATION_BREAK
REGRESSION_RECOVERY
```

---

### 5. 引入多维 Verification Mesh

逐步增加：

- SecurityAgent；
- PerformanceAgent；
- ArchitectureAgent；
- MaintainabilityAgent。

但所有新 Agent 都必须输出结构化 verdict，而不是自由文本。

建议统一格式：

```yaml
verdict:
  dimension: security
  severity: high
  confidence: 0.88
  blocking: true
  message: API key 被硬编码在源码中
  evidence:
    - file: src/config.py
      line: 12
  recommendation: 改为从环境变量读取
```

---

## 五、ASR 后续优化路线图

### Phase 1：显式控制指标

目标：让 ASR 知道自己是否真的在收敛。

重点：

- ConvergenceMetrics；
- error_score；
- improved / stalled / regressed 判断；
- 每轮指标写入事件；
- CLI 展示收敛趋势。

---

### Phase 2：稳定性控制

目标：避免无效循环和 patch 震荡。

重点：

- patch fingerprint；
- failure fingerprint；
- stable diff detection；
- oscillation detection；
- stuck reason 分类；
- 自动切换 RepairMode。

---

### Phase 3：控制 Builder 输出强度

目标：降低修复退化。

重点：

- patch 限幅；
- 文件作用域约束；
- 大 patch 二次确认；
- 局部修复模式；
- 回滚策略升级。

---

### Phase 4：结构化 Analyzer

目标：降低语义裁决噪声。

重点：

- severity；
- confidence；
- evidence；
- affected files；
- blocking；
- 多轮 finding 稳定性判断。

---

### Phase 5：Verification Mesh

目标：从功能正确收敛升级为多维质量收敛。

重点：

- SecurityAgent；
- PerformanceAgent；
- ArchitectureAgent；
- MaintainabilityAgent；
- 多传感器融合；
- 加权误差函数。

---

## 六、最终判断

控制论不是 ASR 的外部装饰，而是 ASR 的底层本质。

ASR 当前已经实现了控制论中的核心闭环：

```text
目标 → 生成 → 验证 → 偏差 → 修复 → 再验证 → 收敛
```

它真正有价值的地方，不是“让 Agent 写代码”，而是：

```text
用运行时系统约束 Agent，
用反馈闭环纠正 Agent，
用事件状态稳定 Agent，
用验证网络裁决 Agent，
最终让不稳定的 LLM 输出收敛为稳定的软件工程结果。
```

因此，ASR 后续最重要的升级方向是：

> **从 Agent Workflow 升级为 Cybernetic Software Runtime。**

也就是：

```text
可观测、可反馈、可调参、可回滚、可收敛、可解释的 AI 软件工程控制系统。
```

如果这个方向继续推进，ASR 的核心竞争力会从“多 Agent 协作”升级为：

> **面向 AI 编程的控制论运行时。**
