
 基于 OpenCode 的 Python 原生自治式 AI 软件工程运行时（Final Architecture）

一、项目定义（Definition）
AI Software Runtime（ASR）是一套：
面向 AI 编程任务的自治式软件工程运行时
其核心目标不是：
让 AI 更会写代码
而是：
让 AI 生成的软件能够稳定收敛
即：
Generate
→ Verify
→ Diff
→ Repair
→ Converge
ASR 本质上：
不是 ChatBot。
不是 Prompt Workflow。
而是：
Agent Framework + Convergence Runtime
即：
带有收敛循环的多 Agent 协作系统

二、核心问题（Why）
当前 AI 编程系统存在四个根本问题：
问题
本质
长任务漂移
无收敛机制
修复破坏旧功能
无全局验证
需求偏离
无语义裁决
无限循环修复
无终止条件
核心问题并不是：
模型不够强
而是：
缺少工程级约束系统
因此：
ASR 的目标不是提升模型能力。
而是：
构建 AI 软件工程运行时

三、第一性原理（First Principles）

3.1 软件开发的本质
软件开发本质不是：
写代码
而是：
持续减少“实现”与“需求”之间的差异
即：
Software Development
=
Continuous Diff Reduction
整个过程：
需求
 ↓
实现
 ↓
验证
 ↓
发现差异
 ↓
修复差异
 ↓
收敛
因此：
软件工程本质是收敛系统

3.2 AI Coding 的根本缺陷
当前 AI Coding：
本质还是：
Next Token Prediction
而不是：
Convergence Runtime
因此：
AI 能生成代码。
但无法保证：
● 正确

● 完整

● 不漂移

● 可维护

● 可持续修复


3.3 ASR 核心哲学
ASR 基于：
“约束大于智能”
即：
稳定的软件系统
=
弱智能
+
强约束
而不是：
超强模型
=
可靠工程

四、系统核心思想（Core Philosophy）

4.1 Generate ≠ Correct
LLM 只能：
生成候选解
不能保证：
正确性
因此：
所有生成结果必须验证
即：
Generate
→ Verify
→ Diff
→ Repair
→ Re-Verify
→ Converge

4.2 去中心化认知
ASR 不允许：
同一个 Agent
既生成又裁决自己
因为：
生成者无法可靠审判自己
因此：
认知职责必须拆分。

4.3 软件工程化 AI
ASR 将：
Prompt Engineering
升级为：
Runtime Engineering
即：
AI概念
ASR对应
Prompt
Spec
Chat
Workflow
Agent
Runtime Node
Context
Runtime State
Retry
Repair Loop
Reflection
Verification
Memory
Event State

五、系统总体架构（Architecture）

5.1 总体结构
                    ┌────────────────┐
                    │    OpenCode    │
                    │     Runtime    │
                    └────────┬───────┘
                             │
                   ┌─────────▼─────────┐
                   │   ASR Controller  │
                   └─────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼

  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │ BuilderAgent │   │ TesterAgent  │   │ AnalyzerAgent│   │SecurityAgent │   │PerformAgent  │   │ArchitectAgent│
  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
         │                  │                  │                  │                  │                  │
         └──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                              │
                                     File-based Event State
                                              │
                                       Structured Diff

六、系统定位（System Position）

OpenCode 负责：
● LLM 调度

● Tool Calling

● Prompt Runtime

● Agent 执行

● Context 管理


ASR 负责：
● 验证

● 收敛

● Diff

● Repair Loop

● 工程约束

● Patch 决策


七、核心模块（Core Agents）

7.1 BuilderAgent（构建Agent）
职责：
● 代码生成

● Patch 修复

● Refactor

● 文件修改

特点：
● 可保留长期上下文

● 允许 Memory

● 负责“创造”

Builder 是：
系统唯一允许长期状态的 Agent

7.2 TesterAgent（测试裁决Agent）
职责：
● pytest

● 单元测试

● 边界测试

● 异常测试

● 回归验证

输出：
{
  "passed": false,
  "errors": [],
  "coverage": 0.82
}
特点：
Stateless
即：
每轮重新分析。
防止：
错误污染

7.3 AnalyzerAgent（语义裁决Agent）
职责：
● 需求对齐

● Spec Diff

● Feature Check

● Constraint Validation

输出：
{
  "missing_feature": [],
  "logic_issue": [],
  "constraint_violation": []
}
作用：
第二层裁决

八、双层裁决系统（Layered Verification）
这是 ASR 最核心的创新。

第一层：硬约束裁决
验证：
代码是否正确运行
包括：
● pytest

● 编译

● lint

● coverage

● runtime error

由：
TesterAgent
负责。

第二层：语义裁决
验证：
实现是否符合需求
包括：
● 功能遗漏

● 逻辑偏差

● Spec 不一致

● 错误实现

由：
AnalyzerAgent
负责。

九、系统运行机制（Runtime）

9.1 核心收敛循环
系统本质：
Generate
→ Verify
→ Diff
→ Repair
→ Verify
→ Converge
而不是：
Prompt
→ Output

9.2 Runtime 控制逻辑与状态机

Controller 驱动以下状态机收敛循环：

States:
  INIT → GENERATING（绿场项目）→ TESTING → ANALYZING → REPAIRING → CONVERGED/STUCK

每轮迭代：
  1. TESTING：TesterAgent 执行 compile→lint→pytest→coverage
  2. 若测试通过：
     a. ANALYZING：AnalyzerAgent + SecurityAgent + PerformanceAgent + ArchitectureAgent
     b. 若 spec_aligned 且无 high-severity mesh 问题 → CONVERGED
     c. 若 mesh 发现 high-severity 问题 → REPAIRING
  3. 若测试失败 → REPAIRING：BuilderAgent 生成 unified diff patch
  4. Controller 应用 patch（PatchEngine），下一轮重新 TESTING

回滚机制：
  若 patch 导致测试失败数增加（退化），Controller 自动回滚到修补前状态。

9.3 收敛终止条件
条件	作用
最大迭代次数	防止无限循环
Diff稳定	相同 patch 连续出现 N 次 → STUCK
Patch震荡	两个 patch 交替出现 → STUCK
Patch失败	patch 应用失败 → STUCK
测试通过 + Spec一致 + Mesh安全	全部通过且无 high-severity 安全问题 → CONVERGED

注：SecurityAgent/PerformanceAgent/ArchitectureAgent 的 high-severity 发现会阻止收敛。

9.4 Controller 职责与边界

ASRController 是系统的主动编排引擎，不是薄适配层。

Controller 负责：
  ● 收敛循环状态机：驱动 INIT → GENERATING → TESTING → ANALYZING → REPAIRING → CONVERGED/STUCK
  ● Agent 编排：按事件协议调用 Builder/Tester/Analyzer/Mesh Agents
  ● Patch 管理：通过 PatchEngine 应用 unified diff 到项目文件
  ● 回滚裁决：检测退化（失败数增加）→ 自动回滚到修补前状态
  ● 终止裁决：评估 max_iterations / stable_diff / patch_oscillation / patch_failed / spec+mesh 条件
  ● 事件审计：所有状态转换产生结构化事件（完整审计轨迹）

Controller 不负责：
  ● 代码生成（BuilderAgent）
  ● 测试执行（TesterAgent）
  ● 语义分析（AnalyzerAgent）
  ● 安全/性能/架构分析（SecurityAgent/PerformanceAgent/ArchitectureAgent）

十、本地化 A2A（Agent-to-Agent）
ASR 不采用：
● Kafka

● NATS

● 微服务

● 分布式总线

原因：
MVP阶段复杂度过高
因此：
ASR 使用：
文件化 A2A 协议

10.1 Event File
所有 Agent 通信：
统一通过结构化事件文件。
例如：
{
  "event_id": "uuid",
  "task_id": "task_001",

  "type": "TEST_FAILED",

  "from": "tester",
  "to": "builder",

  "payload": {
    "file": "main.py",
    "error": "AssertionError"
  }
}

10.2 Runtime 目录结构
.runtime/
├── events/
├── inbox/
│   ├── builder/
│   ├── tester/
│   └── analyzer/
├── tasks/
├── patches/
├── diffs/
└── state/

10.3 文件化 A2A 的双重作用

文件化 A2A 协议有两个互补目的：

1. 审计与回放（Primary）：
   所有 Controller-Agent 交互产生结构化事件文件。
   事件流可完整回放，重建任意时刻的系统状态。
   这是 §11.2 Event-based State 的基础。

2. 解耦通信（Secondary）：
   Agent 之间不直接互相依赖。Controller 作为唯一协调中枢。
   直接调用模式（默认）：Controller 通过 Agent.process(event) 驱动执行。
   解耦模式（--decoupled）：Agent 通过 AgentRunner 独立轮询 inbox。
   两种模式产生相同的事件流，可在运行时切换。

核心原则：
   Agent 的认知职责分离（Builder ≠ Tester ≠ Analyzer），
   而非通信介质分离。

十一、状态系统（State System）

11.1 为什么不能依赖 Context
LLM Context：
● 不稳定

● 会污染

● 会漂移

● 会遗忘

因此：
Runtime 状态必须外部化

11.2 Event-based State
系统真实状态：
来源于：
事件流
例如：
TaskCreated
CodeGenerated
TestFailed
PatchGenerated
SpecRejected
PatchAccepted
Runtime 根据事件：
重建系统状态。

十二、Spec 系统（Specification System）

12.1 Spec 输入方式

ASR 支持两种 Spec 输入方式：

1. 结构化 YAML（推荐，Primary）：
   直接编写 YAML spec 文件，可靠性最高。
   示例见 demo_project/spec.yaml。

2. 自然语言编译（Convenience）：
   通过 SpecCompiler 将自然语言需求编译为 Structured Spec。
   适用于快速原型，但结果需人工审核。

12.2 为什么必须结构化 Spec
因为：
无结构需求无法验证
这是：
AI Coding 最大问题之一。

十三、Diff 驱动修复（Diff-driven Repair）
ASR 不直接：
重新生成整个项目
而是：
基于 Diff 局部修复
即：
发现差异
→ 生成Patch
→ 验证Patch
→ 收敛
这是：
成本控制核心

十四、系统阶段路线（Roadmap）

Phase 1：Single Runtime MVP
目标：
实现：
Generate
→ Verify
→ Repair
能力：
● Builder

● Tester

● Analyzer

● 本地状态


Phase 2：File-based A2A
增加：
● Event Log

● Inbox

● Event Replay

实现：
本地自治 Runtime

Phase 3：Task DAG
增加：
● 子任务拆解

● Patch级验证

● 局部修复


Phase 4：Verification Mesh
增加：
● SecurityAgent

● PerformanceAgent

● ArchitectureAgent

形成：
多维裁决网络

Phase 5：Autonomous Engineering Runtime
最终：
ASR 成为：
OpenCode 的自治工程运行时层

十五、关键设计原则（Critical Principles）

原则1：裁决Agent必须无状态
即：
● Tester

● Analyzer

每轮重新分析。
防止：
错误累积

原则2：Builder允许长期上下文
因为：
Builder 负责：
长任务连续性

原则3：永远不要让 AI 自己定义成功
必须：
外部验证

原则4：局部修复优于全局重写
因为：
全量重生成最容易漂移

原则5：收敛优于智能
ASR 的核心：
不是：
更聪明
而是：
更稳定

十六、技术栈（Tech Stack）
严格限制：
仅 Python

推荐技术
模块
技术
Runtime
Python 3.12
Agent Runtime
OpenCode
状态存储
JSON / YAML
Patch系统
unified diff
测试
pytest
Sandbox
subprocess
Event State
文件系统
配置
YAML

十七、核心价值（Value）

相比单Agent
ASR：
● 更稳定

● 可收敛

● 可验证

● 不易漂移


相比 Claude Code 类系统
ASR：
● 更低成本

● 更强工程约束

● 更可控

● 可私有化


十八、最终系统本质（Final Definition）
ASR 本质不是：
AI Coding Tool
而是：
AI Software Convergence Runtime
即：
一个让 AI 软件开发
从“生成问题”
变成“工程收敛问题”
的运行时系统

十九、最终结论（Conclusion）
ASR 的核心创新：
不是：
“让 AI 更强”
而是：
“让 AI 在工程约束下稳定收敛”
最终实现：
低成本模型
+
多Agent协作
+
验证驱动
+
差异修复
+
工程约束
=
高稳定性 AI 软件开发系统

附件

某开发（workbuddy）任务类型分布（36个任务，04-14 ~ 04-23）
类型
数量
占比
发现Bug
17
43.6%
新需求
7
23.1%
Review
6
15.4%
改需求
5
10.3%
需求未实现
2
5.1%
其他
2
5.1%

