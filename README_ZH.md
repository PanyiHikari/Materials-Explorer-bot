[English](README.md)

# Materials Project Bot

一个基于 [NoneBot2](https://github.com/nonebot/nonebot2) 的 QQ 机器人插件，接入 [Materials Project](https://materialsproject.org/) API，在群聊中查询晶体结构、搜索材料、获取 CIF 文件，并通过 [VESTA](https://jp-minerals.org/vesta/) 渲染晶体结构图片。此外，插件还接入了 DeepSeek，可以在群聊中自动识别自然语言形式的晶体查询意图并代为执行。

---

## 功能特性

- **材料查询**：通过 `material_id`（如 `mp-162`）获取对称化 CIF 文件
- **结构渲染**：调用 VESTA 渲染晶体结构的默认视图或指定晶面投影图
- **三视图**：`tri` 参数一次渲染沿 (100)、(010)、(001) 三个方向的正交投影
- **材料搜索**：支持按「仅含元素」「至少含元素」「化学式」三种模式自动匹配搜索
- **分页浏览**：搜索结果按每页 10 条展示，支持 `nextp` / `lastp` 翻页
- **序号引用**：直接引用搜索结果中的序号获取 CIF 或渲染图片
- **AI 消息监听**：可选用 DeepSeek 分析群聊消息，自动识别自然语言中的晶体查询意图
- **冷却机制**：按群聊独立计时，防止滥用
- **管理指令**：支持群级开关、冷却重置和 AI 监听开关

---

## 安装

### 1. 安装 NoneBot2 与适配器

如果你还没有 NoneBot2 项目，请先参考[官方文档](https://nonebot.dev/docs/quick-start)创建一个：

```bash
pip install nonebot2 nonebot-adapter-onebot
```

### 2. 安装插件依赖

```bash
pip install mp-api pymatgen openai
```

- `mp-api` / `pymatgen`：Materials Project API 与晶体学工具
- `openai`：以 OpenAI 兼容格式调用 DeepSeek API（AI 监听功能）

### 3. 安装 VESTA

从 [VESTA 官网](https://jp-minerals.org/vesta/en/download.html) 下载对应系统的版本并安装。

> **重要提示**
> - **Windows / macOS**：官方提供预编译版本，安装后即可使用。
> - **Linux**：官方**没有**提供 Linux 二进制版本。如需在 Linux 服务器上运行，请使用 [Wine](https://www.winehq.org/) 运行 Windows 版本，并配合 `Xvfb` 虚拟显示环境。
> - VESTA 是 GUI 程序，运行时需要可用的显示环境（Windows/macOS 桌面或 Linux 的 Xvfb）。

### 4. 安装插件

将 `materials_project` 目录放入 NoneBot2 项目的 `plugins` 目录下：

```
your_bot_project/
├── plugins/
│   └── materials_project/
│       ├── __init__.py
│       ├── config.py
│       ├── mp_api.py
│       ├── render_vesta.py
│       ├── search.py
│       ├── cooldown.py
│       ├── admin.py
│       ├── watch.py
│       └── ai_watcher.py
├── .env
└── pyproject.toml
```

然后在 `pyproject.toml` 中确认插件已加载：

```toml
[tool.nonebot]
plugins = ["materials_project"]
```

---

## 配置

在项目根目录的 `.env` 文件中添加以下配置：

```env
# Materials Project API Key（必填）
# 前往 https://materialsproject.org/api 申请
MP_API_KEY=your_api_key_here

# VESTA 可执行文件路径（必填）
# Windows 示例：C:/Program Files/VESTA/VESTA.exe
# macOS 示例：/Applications/VESTA/VESTA.app/Contents/MacOS/VESTA
# Linux 示例：/usr/local/bin/VESTA
VESTA_EXEC=C:/Program Files/VESTA/VESTA.exe

# 图片生成超时时间（秒，可选，默认 30）
IMAGE_TIMEOUT=30

# 搜索结果每页条数（可选，默认 10）
SEARCH_PAGE_SIZE=10

# DeepSeek API Key（可选，AI 消息监听功能需要）
# 前往 https://platform.deepseek.com/ 申请
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

配置字段会自动映射到 `config.py` 中的 `Config` 模型（NoneBot2 会自动把环境变量转为小写字段名）。

---

## 使用方法

所有指令**仅在 bot 被 @ 时响应**（`nextp` / `lastp` 除外）。

### 基本指令

| 指令 | 说明 |
|---|---|
| `/mp <material_id>` | 获取指定材料的对称化 CIF 文件 |
| `/mp.prev <material_id>` | 沿默认 (113) 晶面投影渲染晶体结构图片 |
| `/mp.prev <material_id> <view>` | 沿指定晶面（如 `011`、`111`）投影渲染 |
| `/mp.prev <material_id> tri` | 三视图，依次发送沿 (100)、(010)、(001) 的三张图片 |
| `/mp.help` | 显示指令索引 |

### 搜索与引用

| 指令 | 说明 |
|---|---|
| `/mp.search <条件>` | 搜索材料，每页 10 条 |
| `nextp` / `lastp` | 翻页（无需 @，无需 `/`，无冷却） |
| `/mp.res <序号>` | 获取搜索结果中指定序号的 CIF |
| `/mp.res.prev <序号>` | 渲染搜索结果中指定序号的默认 (113) 视图 |
| `/mp.res.prev <序号> <view>` | 渲染搜索结果中指定序号的投影图 |
| `/mp.res.prev <序号> tri` | 渲染搜索结果中指定序号的三视图 |
| `/mp.res.CLR` | 清除本群搜索结果 |

**搜索条件自动匹配规则：**

| 输入示例 | 匹配模式 | 说明 |
|---|---|---|
| `Si-O` | 仅含元素 | 材料中只含 Si 和 O |
| `Li-Fe-P-O` | 仅含元素 | 材料中只含 Li、Fe、P、O |
| `Si,O` | 至少含元素 | 材料中至少含 Si 和 O |
| `Fe,Co,Ni` | 至少含元素 | 材料中至少含 Fe、Co、Ni |
| `Fe2O3` | 化学式 | 按化学式精确匹配 |

**搜索结果表格格式：**

```
| 序号 | 是否测得 | Materials ID | 化学式 | 空间群 | 原子数 |
| --- | --- | --- | --- | --- | --- |
| 1 | * | mp-162 | SiO2 | P3_121 | 9 |
| 2 |  | mp-554215 | K2Si4O9 | P6/mmm | 30 |
...

第1页，共5页
```

### 管理指令

| 指令 | 说明 |
|---|---|
| `/mp.SWT` | 切换本群插件启用/禁用状态（默认启用） |
| `/mp.CD` | 将本群所有冷却时间归零 |
| `/mp.WATCH` | 切换本群 AI 消息监听状态（默认关闭） |

### 冷却机制

- `/mp`、`/mp.prev` **共用**一个冷却计时器，时长 **1 分钟**
- `/mp.search` 单独计时，时长 **1 分钟**
- `/mp.res`、`/mp.res.prev` 共用一个**滑动窗口**计时器，**每 1 分钟内最多调用 3 次**（从第一次调用起算）
- 冷却时间**按群聊独立计算**
- 翻页指令 `nextp` / `lastp` **无冷却**
- AI 监听触发的调用**不消耗冷却**

### AI 消息监听

开启 `/mp.WATCH` 后，插件会监听群聊中的消息，并交给 DeepSeek 分析是否包含晶体查询意图。

**支持的自然语言示例：**

| 群消息 | AI 判断并调用 |
|---|---|
| `查 YBa2Cu3O7 的结构` | `/mp.search YBa2Cu3O7` |
| `@bot 查 SiO2 的结构` | `/mp.search SiO2` |
| `给出 7 号沿 122 晶面的投影` | `/mp.res.prev 7 122` + `/mp.res 7` |
| `查 12 号的结构` | `/mp.res.prev 12` + `/mp.res 12` |
| `mp-162 长什么样` | `/mp.prev mp-162` |

**通知机制**：AI 调用指令前，会先发送一条 `正在调用 /mp.search SiO2` 形式的提示消息。

**过滤规则：**

- `@bot` 的消息**不受长度限制**
- 非 `@bot` 的消息，**超过 100 字符则跳过分析**
- 消息本身是 MP 指令（如 `@bot /mp.search SiO2`）时**跳过分析**，直接由指令机制执行
- 空消息跳过

> 注意：AI 监听功能需要配置 `DEEPSEEK_API_KEY`，否则即使开启开关也不会产生任何响应。

---

## 项目结构

```
materials_project/
├── __init__.py        # 插件入口，事件响应器注册与指令处理
├── config.py          # 配置模型（从 .env 读取）
├── mp_api.py          # Materials Project API 封装
├── render_vesta.py    # VESTA 渲染与图片导出
├── search.py          # 搜索结果缓存与分页管理
├── cooldown.py        # 按群聊的冷却时间管理
├── admin.py           # 群级启用/禁用状态管理
├── watch.py           # 群级 AI 消息监听开关管理
└── ai_watcher.py      # DeepSeek 调用、工具定义、消息过滤
```

### 模块职责

| 模块 | 职责 |
|---|---|
| `mp_api.py` | 封装 `MPRester`，提供获取结构、生成 CIF、搜索材料等异步接口 |
| `render_vesta.py` | 调用 VESTA 命令行渲染 CIF 并导出 PNG，支持默认视图与晶面投影 |
| `search.py` | 维护每个群聊的搜索缓存，处理分页格式化（含表头） |
| `cooldown.py` | 维护每个群聊的三类冷却计时器 |
| `admin.py` | 维护每个群聊的启用状态 |
| `watch.py` | 维护每个群聊的 AI 监听开关状态 |
| `ai_watcher.py` | 定义 DeepSeek 工具、过滤规则、消息分析接口 |

---

## 关于 VESTA 渲染

### 命令行调用方式

插件通过如下命令行参数调用 VESTA：

```bash
VESTA -open structure.cif -export_img output.png -close
```

指定晶面投影时附加旋转参数：

```bash
VESTA -open structure.cif -rotate_x a -rotate_y b -export_img output.png -close
```

其中旋转参数 `a`、`b` 的计算方法如下：

```python
# pymatgen 的 lattice.matrix 行向量为 a, b, c
lat = np.array(structure.lattice.matrix)
# 倒格基：列向量为 a*, b*, c*
recip = np.linalg.inv(lat).T

# (hkl) 晶面法线方向在笛卡尔坐标中的向量
normal = h * recip[:, 0] + k * recip[:, 1] + l * recip[:, 2]
norm = np.linalg.norm(normal)
if norm < 1e-12:
    return 0.0, 0.0, 0.0
vx, vy, vz = normal / norm

# 步骤 1：绕 x 轴旋转 a，使 vy -> 0
a = float(np.degrees(np.arctan2(vy, vz)))

# 步骤 2：绕 y 轴旋转 b，使 vx -> 0
v_z_after_x = float(np.sqrt(vy ** 2 + vz ** 2))
b = float(np.degrees(np.arctan2(-vx, v_z_after_x)))

return a, b, 0.0
```

### 默认视角与三视图

- **默认视角**：不指定 `view` 参数时，按 (113) 晶面投影渲染
- **三视图**：`view` 参数为 `tri`（不区分大小写）时，依次渲染 (100)、(010)、(001) 三张投影图并连续发送

### 已知限制

- VESTA 的 `-export_img` 参数只负责导出图片，**不会让程序自动退出**，因此插件在检测到 PNG 生成后会**主动终止 VESTA 进程**。
- VESTA 命令行只暴露 `-rotate_x/y/z` 欧拉角参数。插件通过反三角函数把 `(hkl)` 法线方向转换为旋转角，实现精确对齐；但如果 VESTA 的旋转约定（右手定则 / 施加顺序）与推导不同，可能出现方向反向或轻微偏斜。
- Linux 无头服务器需要 `Xvfb` 虚拟显示：

  ```bash
  xvfb-run -a /path/to/VESTA -open structure.cif -export_img output.png -close
  ```

  或在 `render_vesta.py` 的 `Popen` 参数前加上 `["xvfb-run", "-a"]`。

---

## 获取 DeepSeek API Key

1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)。
2. 注册并登录账号。
3. 左侧菜单 **「API keys」** → 点击 **「创建 API KEY」**。
4. 输入名称（如 `nonebot-mp`），点击创建。
5. **立即复制生成的 Key**（形如 `sk-xxxxxxxx`），关闭弹窗后无法再次查看完整 Key。
6. 可能需要充值后才能使用 API（按 token 计费）。

> 本插件使用标准的 OpenAI 兼容接口调用 DeepSeek，**不需要任何 skill 文件**——工具定义直接写在 `ai_watcher.py` 的 `TOOLS` 列表中。

---

## 常见问题

<details>
<summary><b>插件加载时提示 <code>No module named 'mp_api'</code></b></summary>

未安装 Materials Project SDK。在虚拟环境中执行：

```bash
pip install mp-api pymatgen
```
</details>

<details>
<summary><b>插件加载时提示 <code>No module named 'openai'</code></b></summary>

未安装 OpenAI SDK（用于调用 DeepSeek）。执行：

```bash
pip install openai
```
</details>

<details>
<summary><b>渲染时提示 <code>VESTA 可执行文件未找到</code></b></summary>

检查 `.env` 中 `VESTA_EXEC` 是否填写正确的**绝对路径**，或确保 VESTA 已加入系统 `PATH`。
</details>

<details>
<summary><b>渲染时提示 <code>VESTA 进程超时被终止</code>，但图片已生成</b></summary>

这是正常现象。VESTA 导出图片后不会自动退出，插件在检测到图片生成后会主动终止进程。该警告可以忽略。
</details>

<details>
<summary><b>搜索时返回空结果</b></summary>

1. 确认 `MP_API_KEY` 有效。
2. 尝试用更宽泛的条件，如 `Si-O` 改为 `Si,O`。
3. 查看后台日志中的搜索参数和返回结果数量，判断是 API 语义问题还是确实没有结果。
</details>

<details>
<summary><b>字段报错 <code>invalid fields requested: ['is_experimental']</code></b></summary>

Materials Project API 已移除 `is_experimental` 字段，改用 `theoretical`（`theoretical=False` 表示实验结构）。请确保 `mp_api.py` 中字段名正确。
</details>

<details>
<summary><b>冷却时没有任何输出</b></summary>

检查 `_check_enabled_and_cooldown` 函数是否接收 `bot` 参数，并使用 `bot.send(event, ...)` 而非 `event.bot.send(...)`。`GroupMessageEvent` 没有 `.bot` 属性。
</details>

<details>
<summary><b>开启 <code>/mp.WATCH</code> 后 AI 监听无任何输出</b></summary>

按以下顺序排查：

1. 确认 `.env` 中的 `DEEPSEEK_API_KEY` 已正确配置，且**重启过 bot**。
2. 确认在群内发送过 `@bot /mp.WATCH`，且 bot 回复了 `AI 消息监听已开启`。
3. 检查消息是否符合过滤规则（是否太长、是否是 `/mp*` 指令）。
4. 在 `handle_ai_watch` 中临时加 `logger.info` 输出，观察是开关、过滤还是 API 调用环节拦下了消息。
</details>

<details>
<summary><b>AI 监听误触发 / 触发频率过高</b></summary>

- 若所有消息都被送 AI，可考虑在 `should_analyze` 中加入关键词预筛（如必须包含"查/结构/CIF/投影/晶面/号"等词才送 AI）。
- 若个别无关消息触发了指令，可临时将 `tool_choice="auto"` 保持不动，但在 `analyze_message` 的系统提示词中收紧约束。
- 关闭 `/mp.WATCH` 即可完全停止 AI 监听。
</details>

---

## 贡献

欢迎提交 Issue 和 PR。如果你实现了以下功能，非常欢迎分享：

- [ ] 精确 `[hkl]` 投影（通过预置 `.vesta` 模板）
- [ ] Linux + Xvfb 的自动适配
- [ ] 支持更多渲染后端（如 ASE、py3Dmol）
- [ ] 支持按空间群、带隙、稳定性等条件筛选
- [ ] 支持多种 AI 后端（OpenRouter、Ollama 等）

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 致谢

- [Materials Project](https://materialsproject.org/) —— 提供开放的材料数据库与 API
- [NoneBot2](https://github.com/nonebot/nonebot2) —— 优秀的 Python 异步机器人框架
- [VESTA](https://jp-minerals.org/vesta/) —— 强大的晶体结构可视化工具
- [pymatgen](https://pymatgen.org/) —— 材料科学 Python 工具库
- [DeepSeek](https://platform.deepseek.com/) —— 提供兼容 OpenAI 接口的推理服务

---

## 免责声明

本插件仅供学习和科研使用。使用 Materials Project API 时请遵守其[使用条款](https://materialsproject.org/terms-of-use)，使用 DeepSeek API 时请遵守其平台服务条款。