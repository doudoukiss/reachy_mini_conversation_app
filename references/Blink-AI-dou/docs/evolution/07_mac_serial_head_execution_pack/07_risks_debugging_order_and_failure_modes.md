# 风险点、排错顺序与失败模式

## 一、总原则

排错顺序永远是：

1. **链路**
2. **读数**
3. **校准**
4. **单机动作**
5. **多机动作**
6. **语义动作**
7. **AI 自动化**

不要倒过来。

---

## 二、风险点总表

### 1. 串口端口问题
表现：
- 看不到设备
- port 打不开
- 连接后又消失

优先排查：
- 线缆
- URT-1 / USB 转串口板
- Mac 设备节点变化
- 端口被别的程序占用

### 2. 波特率问题
表现：
- scan 全失败
- 偶发响应
- 某些 ID 有，某些没有

优先排查：
- 115200
- 1000000
- 某个舵机曾被改过 baud

### 3. 电源 / 总线稳定性问题
表现：
- 静态能读，动作就掉线
- 单机可动，多机不稳
- health 读数突然异常

优先排查：
- 电源功率
- 接线粗细
- 共地
- 多机同时动作电流峰值

### 4. calibration 问题
表现：
- transport healthy 但 motion gate 不开
- 动作方向错误
- neutral 不对
- 左右镜像不对称

优先排查：
- calibration 还是 template
- neutral capture 是否真实保存
- profile / calibration 是否混用旧文件

### 5. 机械干涉
表现：
- 某个 joint 到某值就卡
- readback 偏差大
- 动作有异响
- 某个表情特别不自然

优先排查：
- raw_min/raw_max 太宽
- coupling 过强
- 安装位置偏了
- linkage 有摩擦

### 6. runtime 接管问题
表现：
- CLI 可以动，runtime 不动
- runtime 动了但 console 看不见状态
- AI 以为动作成功，其实失败

优先排查：
- env 配置
- runtime mode
- body driver
- transport mode
- console state / snapshot / error propagation

---

## 三、推荐排错顺序

### Step 1：只做 doctor
目标：确认 port、baud、ID 在线情况。

### Step 2：只做 read-position/read-health
目标：确认不是“只能 ping，不能读”。

### Step 3：保存 live calibration
目标：解除 template gate。

### Step 4：单机关节小动作
目标：验证方向和限位。

### Step 5：小组联动
目标：验证同步写和供电。

### Step 6：semantic smoke
目标：验证 compiler + bridge + transport。

### Step 7：runtime 接管
目标：验证 console、local companion、artifact。

---

## 四、强制停止条件

出现以下情况必须立即停：

- 多机动作时明显掉压或总线大面积超时
- 机械结构出现明显卡顿 / 异响 / 拉扯
- 某个关节多次撞限位
- calibration 与 profile 明显冲突
- runtime 在动作失败时仍继续高频下发命令

---

## 五、成功开发流程的最小闭环

一个真正健康的开发闭环应该是：

1. `blink-serial-doctor`
2. `body-calibration read-position`
3. `body-calibration write-neutral`
4. `body-calibration semantic-smoke`
5. `uv run blink-appliance`
6. `/console` 观察 body 状态
7. 导出 artifact
8. 根据 artifact 调整 calibration / compiler / semantics

如果缺了其中任意一段，这条链就还不够 world-class。
