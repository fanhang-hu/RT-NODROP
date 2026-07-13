# 面向泛在系统的调度

本项目面向工业物联网（IoT）场景中的边缘控制节点。此类节点通常部署在产线设备、机器人工作站或现场网关侧，需要在有限的计算资源上并行执行传感采集、运动/过程控制、设备通信和边缘数据处理等任务。这些任务直接作用于物理过程，既要在确定的时间窗口内完成，也要在设备接入、进程行为和系统调用发生时保留可追溯的安全记录。

项目以 RT-NoDrop 为实验原型，将控制、感知、通信等功能任务与系统调用审计、事件消费等安全任务统一纳入可调度性分析。在保证功能任务 deadline 的同时，框架为安全事件从产生到处理完成的驻留时间给出上界，并通过 CPU 利用率、系统调用强度和 CPU 数量三个维度，对比基础 RTA、OmniLog、Audit、Ellipsis 与 NoDrop 等策略的可调度率及事件处理时延。

作者团队：东南大学网络空间安全学院

队长：胡樊航

队员：薛烁敏、吕宇峰、张涵、裘珑颖

## 1. 项目背景与目标

在典型的工业边缘节点中，控制回路、图像/传感数据处理、设备协议通信与安全审计会同时竞争 CPU、内存和内核缓冲区。安全审计不是独立于业务的离线日志工作：每次系统调用、设备访问或进程行为都可能产生事件，事件需要先写入内核缓冲区，再由 consumer 进行处理、过滤与持久化。若调度器忽略这部分开销，负载升高时便会出现两类风险：功能任务的响应时间失去确定性，或安全事件在缓冲区中滞留过久、发生丢失，进而削弱设备运行的可追溯性。

现有处理方式往往偏向其中一个目标：集中式 consumer 易在高事件速率下形成跨任务、跨核干扰；同步处理能缩短事件等待，却会把额外开销直接放到系统调用路径上；按事件积压再批量处理虽然节省唤醒次数，却难以给处理时长和事件等待时间设定稳定边界。

对于需要持续感知、控制和安全监测的 IoT 节点，这三类开销都必须成为调度决策的一部分。本项目的目标是建立**功能任务—安全事件—审计 consumer—调度分析**的一体化模型：把每个功能任务的审计记录开销计入 WCET，把事件 consumer 作为显式的可调度实体，并在分区固定优先级模型下共同分析功能任务响应时间与事件驻留时间。由此，系统能够同时回答三个问题：

- 在给定 CPU 资源和业务负载下，控制、感知与通信任务能否满足 deadline；
- 安全事件是否能够在有界时间内被 consumer 处理，从而避免无限积压；
- 当事件强度或 CPU 规模变化时，哪种审计处理策略能以更小的调度干扰保持系统可用。

## 2. 核心能力

- **统一任务模型**：功能任务的系统调用跟踪开销与审计 consumer 的执行开销均进入同一响应时间分析模型。
- **多框架协同对比**：统一实验框架对比基础 RTA、OmniLog、Audit、Ellipsis、NoDrop 等策略，量化不同安全处理方式对实时性的影响。
- **多核/多分区扩展**：支持按 CPU 分区生成任务集，扫描 CPU 数量以观察多核边缘节点上的混部扩展趋势。
- **安全任务完整性保障**：除功能任务 deadline 外，输出 NoDrop 安全事件的最大、最小和平均驻留时间。
- **可复现实验**：固定随机种子、参数化命令行入口、结构化实验输出，便于重复运行与横向比较。

## 3. 设计特点与适用边界

| 设计关注点 | 项目实现 | 适用边界 |
| --- | --- | --- |
| 轻量化模块组合 | 任务生成、审计开销建模、RTA、NoDrop 分析和实验编排相互解耦；策略参数集中于 `params.py` | 当前实现为 Python/SchedCAT 实验框架 |
| 功能与安全协同 | 将功能任务与安全审计开销统一映射为可调度实体，并比较不同审计策略造成的资源竞争 | 已覆盖安全审计机制之间的协同影响，尚未对接 K8s、Spark 等资源平台 |
| 混合负载与多核扩展 | 功能任务与 consumer 混部；consumer 可被高优先级功能任务或 consumer 抢占；支持多 CPU 分区 | 覆盖实时功能任务和安全任务混部，未实现通用 DAG 或 fork-join 运行时 |
| 工业边缘建模 | 通过利用率、系统调用强度、CPU 数量扫描模拟不同资源压力与设备规模 | 为可重复的分析验证，尚未绑定具体机器人或物理设备 |

本仓库的重点是安全感知实时调度。其核心价值在于使安全任务成为**可见、可分析、可调度**的系统负载；后续可在保持这一模型不变的基础上，接入边云设备、动态任务拆分或机器人仿真平台。

## 4. 技术方案概览

### 4.1 三层融合模型

| 层级 | 主要对象 | 作用 |
| --- | --- | --- |
| 功能任务层 | 控制、感知、通信等周期/ sporadic 任务 | 描述周期、WCET、deadline、系统调用次数 |
| 安全审计层 | syscall 跟踪、事件缓冲、审计 consumer | 显式描述记录与消费安全事件的资源开销 |
| 调度分析层 | 分区固定优先级响应时间分析 | 同时判断功能任务可调度性与事件驻留时间上界 |

对功能任务 $\tau_i=(e_i,p_i,s_i)$，其中 $e_i$ 为原始 WCET、$p_i$ 为周期（亦为隐式 deadline）、$s_i$ 为每个 job 的系统调用上界。引入单次审计记录开销 $\Delta$ 后，扩展执行时间为：

$$E_i=e_i+s_i\Delta$$

NoDrop 为每个功能任务派生安全事件 consumer。consumer 与功能任务共同参与优先级分析，因此安全处理不再是调度器不可见的后台负载。详尽模型、公式与参数含义见[框架设计文档](RT-NoDrop/docs/feature_design.md)。

### 4.2 评测策略

| 策略 | 作用 |
| --- | --- |
| RTA | 不含安全审计处理开销的功能实时性基线 |
| OmniLog / Audit / Ellipsis | 以集中 consumer 处理安全事件的对照策略 |
| NoDrop | 为功能任务绑定 consumer、显式保障安全事件处理的安全感知策略 |

### 4.3 输出指标

| 指标 | 含义 | 系统意义 |
| --- | --- | --- |
| 可调度率 | 满足 deadline 的任务集比例 | 实时响应能力、混部调度效果 |
| CPU 利用率 | 不同资源压力下的可调度性变化 | 资源利用率与负载适应性 |
| 系统调用强度 | 不同安全负载下的可调度性变化 | 安全任务与功能任务协同 |
| CPU 数量 | 多分区资源规模变化下的可调度性 | 多核/多设备扩展趋势 |
| `RES_MAX_ND` / `RES_MEAN_ND` | RT-NoDrop 安全事件最大/平均驻留时间 | 安全任务完整性与及时性 |

## 5. 仓库结构

```text
.
├── README.md                         # 项目总览与复现导航（本文件）
├── Plan document.md / .pdf           # 完整技术方案
├── User Manual.md / .pdf             # 部署、运行与实验操作说明
├── entire environment.pdf / .pptx    # 项目展示材料
└── RT-NoDrop/
    ├── README.md                      # 原始实验框架依赖与基础说明
    ├── setpath.sh                     # SchedCAT/CPLEX 环境变量示例
    ├── rta/
    │   ├── safety_aware_sched.py      # 参数化实验主入口
    │   ├── util_syscall_cpu.py        # 任务集生成与测试集合
    │   ├── params.py                  # 审计框架开销参数
    │   ├── rta.py                     # 基础响应时间分析
    │   ├── rta_omnilog.py             # 集中式 consumer 分析
    │   ├── rta_ellipsis.py            # Ellipsis 对照分析
    │   └── rta_nodrop.py              # NoDrop 与事件驻留时间分析
    └── docs/
        ├── feature_design.md          # 模型、算法、实现映射与边界
        └── test_plan.md               # 测试用例、指标与通过标准
```

## 6. 文档导航（建议按此顺序阅读）

| 阅读目的 | 文档 | 内容 |
| --- | --- | --- |
| 快速了解项目 | [README.md](README.md) | 项目简介、能力边界、指标和复现入口 |
| 审阅总体技术方案 | [Plan document.md](方案文档.md) / [PDF](方案文档.pdf) | 安全感知实时调度的系统模型、算法与分析 |
| 理解算法与代码映射 | [feature_design.md](RT-NoDrop/docs/feature_design.md) | RTA/NoDrop 公式、consumer 模型、参数与实现位置 |
| 部署并运行实验 | [User Manual.md](使用手册.md) / [PDF](使用手册.pdf) | 环境准备、命令说明、结果查看 |
| 验证结果与复现性 | [test_plan.md](RT-NoDrop/docs/test_plan.md) | 冒烟、正常、异常、边界测试与通过标准 |
| 查阅原始实验依赖 | [RT-NoDrop/README.md](RT-NoDrop/README.md) | SchedCAT、Python 2.7、CPLEX 等基础依赖 |
| 展示材料 | [entire environment.pptx](entire%20environment.pptx) / [PDF](entire%20environment.pdf) | 环境与项目展示材料 |

## 7. 快速复现

### 7.1 环境要求

推荐在 Linux（Ubuntu 14.04/18.04 或兼容发行版）环境复现：

- Python 2.7
- NumPy、SciPy
- GNU Make、SWIG 3.0、g++、libgmp
- Git 子模块中的 SchedCAT
- 可选：IBM CPLEX（部分 SchedCAT 构建环境需要；具体说明见 [RT-NoDrop/README.md](RT-NoDrop/README.md)）

项目沿用了原始 SchedCAT/Python 2.7 实验栈。建议使用容器或兼容 Linux 环境运行，避免将现代 Python 3 环境与原有依赖混用。

### 7.2 初始化与构建

在仓库根目录执行：

```bash
cd RT-NoDrop
git submodule update --init --recursive
source setpath.sh
cd lib/schedcat && make && cd ../../
```

若构建提示找不到 LP Solver，请根据实际 CPLEX 安装位置修改环境变量 `CPLEX_PATH`；详情见 [RT-NoDrop/README.md](RT-NoDrop/README.md)。

### 7.3 冒烟测试

```bash
cd RT-NoDrop
python rta/safety_aware_sched.py \
  --experiment utilization \
  --samples 2 \
  --util-min 0.5 \
  --util-max 0.52 \
  --util-step 0.01 \
  --output-dir output/safety_aware_sched_smoke
```

预期生成 `output/safety_aware_sched_smoke/utilization.txt`。输出应包含 `CONFIGURATION`、`ENVIRONMENT`、`DATA`、`RUN` 四个部分。

### 7.4 完整实验

```bash
cd RT-NoDrop

# 利用率扫描：观察资源压力升高时的可调度率
python rta/safety_aware_sched.py --experiment utilization --samples 1000

# 系统调用强度扫描：观察安全负载变化的影响
python rta/safety_aware_sched.py --experiment syscall_count --samples 1000

# CPU 数量扫描：观察多分区扩展趋势
python rta/safety_aware_sched.py --experiment cpu_count --samples 1000

# 一次执行全部实验
python rta/safety_aware_sched.py --experiment all --samples 1000
```

结果默认写入 `RT-NoDrop/output/safety_aware_sched/`。固定随机种子下，除时间戳和运行耗时外，重复运行的 `DATA` 段应保持一致。

## 8. 基准实验与结果分析

本项目通过随机生成的分区实时任务集，检验审计开销进入调度模型后，各种策略在不同资源压力下能否保证功能任务 deadline，并同时统计安全事件在内核缓冲区中的驻留时间。基准实验的每个参数点随机生成 5,000 组任务集；每个 CPU 分区包含 10 个任务，任务周期均匀取自 10--100 ms。

| 实验维度 | 固定条件 | 扫描范围 | 观察目标 |
| --- | --- | --- | --- |
| 利用率压力 | 1 核、每任务 10 次 syscall | 65%--90% | 资源逐渐饱和时的可调度率 |
| 安全事件强度 | 1 核、利用率 75% | 每任务 5--15 次 syscall | 审计负载增长造成的调度干扰 |
| 多核规模 | 利用率 75%、每任务 2 次 syscall | 1--10 核 | 多分区场景的可扩展性 |
| 高并发利用率压力 | 10 核、每任务 2 次 syscall | 65%--85% | 多核条件下的资源利用能力 |
| 事件驻留时间 | 1 核或 10 核 | 利用率变化 | 安全事件处理的及时性与稳定性 |

### 8.1 可调度性表现

在单核、每任务 10 次 syscall 的压力实验中，RT-NoDrop 在 73% 利用率时仍保持约 100% 的可调度率，升至 75% 时仍达到 93%；集中式 consumer 的 OMNILOG 在 73% 时已降至 92%，随后与 RT-NoDrop 的差距扩大到约 20 个百分点或更高。该结果说明：将各任务的审计处理拆分为受优先级约束的 consumer，能避免全局审计消费者汇聚事件后对高优先级功能任务产生的集中干扰。

当利用率固定为 75%、每任务 syscall 数从 5 增至 15 时，RT-NoDrop 的可调度率始终维持在约 90% 以上；集中式策略和依赖全局处理路径的策略则随事件量增加明显下降。这表明任务级 consumer 将安全事件处理分散到各自的调度上下文后，对事件生成速率变化更稳定。

在多核实验中，RT-NoDrop 的可调度率从 1 核时的 97% 降至 10 核时的 72%。在 5 核扩展到 6 核这一压力突增点，RT-NoDrop 仅下降 1.7 个百分点；OMNILOG、Sysdig、Ellipsis 分别由 81%、86%、87% 降至 66%、71%、72%。这反映出按任务绑定 consumer 的结构能够减少跨核共享 consumer 带来的干扰，具有更平缓的扩展退化趋势。

为综合比较整个扫描区间内的调度能力，实验使用**可调度利用率面积**（Schedulable Utilization Area，SUA）衡量“可调度率--利用率”曲线下的面积。相对各对照策略，RT-NoDrop 的平均 SUA 提升如下：

| 对照策略 | 平均 SUA 提升 | 结果含义 |
| --- | ---: | --- |
| Sysdig | 11.63% | 在相同资源压力范围内，可保持可调度的任务集比例更高 |
| OMNILOG | 21.98% | 避免同步/集中处理带来的高额系统调用与跨任务干扰 |
| Ellipsis | 8.64% | 在实时可调度性上保持稳定优势 |
| Auditd | 850.97% | 在高审计开销下显著扩大可运行的资源区间 |

### 8.2 事件驻留时间表现

功能任务按时完成并不等于安全审计及时完成。因此，实验还统计从事件产生到 consumer 处理完成的驻留时间。

- 在利用率从 50% 升至 70% 以上时，RT-NoDrop 的**最小驻留时间稳定在约 10 ms**。
- RT-NoDrop 的**平均驻留时间**随利用率上升而缓慢增加，约从 62 ms 增至 70 ms；增长来源于高负载下 consumer 受到更多高优先级任务抢占，而非事件无限积压。
- 对照的 Ellipsis 驻留时间约为 90--100 ms，且缺少任务级 consumer 的调度约束。

因此，RT-NoDrop 在提升功能任务可调度性的同时，能够给安全事件处理提供稳定、可量化的时间边界。这种“deadline 保障 + 事件驻留时间约束”的双指标评价方式，适合安全任务与控制、感知、通信任务共用资源的边缘节点。

### 8.3 复现基准扫描

以下命令可按上述参数运行对应扫描。结果保存在指定输出目录中，便于绘制可调度率曲线和驻留时间曲线。

```bash
cd RT-NoDrop

# 单核利用率压力：每任务 10 次 syscall
python rta/safety_aware_sched.py --experiment utilization \
  --num-cpus 1 --syscall-count 10 \
  --util-min 0.65 --util-max 0.90 --util-step 0.01 --samples 5000

# 单核安全事件强度：利用率 75%
python rta/safety_aware_sched.py --experiment syscall_count \
  --num-cpus 1 --util 0.75 \
  --syscall-min 5 --syscall-max 15 --syscall-step 1 --samples 5000

# 多核规模：利用率 75%、每任务 2 次 syscall
python rta/safety_aware_sched.py --experiment cpu_count \
  --util 0.75 --syscall-count 2 \
  --cpu-min 1 --cpu-max 10 --cpu-step 1 --samples 5000

# 10 核利用率压力：每任务 2 次 syscall
python rta/safety_aware_sched.py --experiment utilization \
  --num-cpus 10 --syscall-count 2 \
  --util-min 0.65 --util-max 0.85 --util-step 0.01 --samples 5000
```

## 9. 实验检查

建议在完整扫描前完成以下检查；详细用例见[测试方案](RT-NoDrop/docs/test_plan.md)。

| 检查项 | 命令/方法 | 预期结果 |
| --- | --- | --- |
| CLI 可用性 | `python rta/safety_aware_sched.py --help` | 显示实验参数说明 |
| 冒烟测试 | 采用 2 个样本运行利用率扫描 | 正常退出并生成结果文件 |
| 全量入口 | `--experiment all --samples 1000` | 生成利用率、系统调用强度、CPU 数量三类输出 |
| 可复现性 | 用相同参数与随机种子连续运行两次 | `DATA` 数据一致（时间字段除外） |
| 指标完整性 | 检查输出列 | 包含多策略可调度率及 NoDrop 驻留时间统计 |

## 10. 已知边界与后续扩展

当前代码是面向安全感知实时调度的分析与仿真实验框架，而非已部署的分布式运行时。后续可从以下方向演进：

- 将 consumer 任务映射为 OpenHarmony/Linux 的内核审计服务或安全调度类，并测量真实设备上的开销参数。
- 对接机器人、工业物联网或边云仿真平台，将设备状态、网络时延与任务迁移代价纳入模型。
- 增加任务 DAG、动态拆分、抢占/恢复和跨设备卸载策略，覆盖更一般的嵌套并行场景。
- 使用自适应 consumer 周期、负载预测与多目标优化，在资源利用率、事件驻留时间和 deadline 保障之间动态权衡。

这些扩展不会改变本项目“安全任务必须成为可见、可分析、可调度负载”的核心思想。

## 11. 许可证与致谢

本项目基于 SchedCAT 实验框架开展可调度性分析，相关依赖及许可证信息请参阅子模块与[RT-NoDrop/README.md](RT-NoDrop/README.md)。如使用 IBM CPLEX，请遵循其许可证要求。
