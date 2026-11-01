[English](README.md)

# Materials Project Bot

一个基于 [NoneBot2](https://github.com/nonebot/nonebot2) 的 QQ 机器人插件，接入 [Materials Project](https://materialsproject.org/) API，在群聊中查询晶体结构、搜索材料、获取 CIF 文件，并通过 [VESTA](https://jp-minerals.org/vesta/) 渲染晶体结构图片。插件同时集成 DeepSeek，可自动识别自然语言查询与晶体学提问，并维护按群聊独立的对话记忆和别名字典。

---

## 快速部署

### 1. 环境要求

- Python 3.10+
- 一个已初始化的 [NoneBot2](https://nonebot.dev/docs/quick-start) 项目
- `nonebot-adapter-onebot`（OneBot V11 适配器）
- [VESTA](https://jp-minerals.org/vesta/en/download.html)（GUI 程序，Windows/macOS 可直接安装；Linux 需 Wine + Xvfb）

### 2. 安装依赖

在 NoneBot2 项目的虚拟环境中执行：

```bash
pip install mp-api pymatgen openai
```

### 3. 下载插件

任选一种方式：

- **方式 A（推荐）**：从仓库 Releases 页面下载最新的 `materials_project.zip`，解压到 `plugins/` 目录
- **方式 B**：`git clone` 仓库，将 `materials_project/` 目录复制到项目的 `plugins/` 下

目录结构：

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
│       ├── ai_watcher.py
│       ├── ai_memory.py
│       ├── alias_dict.py
│       ├── alias_dict.json
│       ├── ask_context.py
│       ├── ask_swt.py
│       ├── min_conf.py
│       └── crystallography_skill.md
├── .env
└── pyproject.toml
```

### 4. 配置 `.env`

在项目根目录的 `.env` 中添加：

```env
# ===== 必填 =====
MP_API_KEY=your_materials_project_api_key
VESTA_EXEC=C:/Program Files/VESTA/VESTA.exe

# ===== 可选 =====
IMAGE_TIMEOUT=30
SEARCH_PAGE_SIZE=10

# ===== AI 功能（启用 /mp.WATCH、/mp.ask 时需要） =====
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# AI 监听灵敏度：strict | normal | loose
AI_WATCH_SENSITIVITY=normal
# 自定义关键词（逗号分隔，追加到内置列表）
AI_WATCH_KEYWORDS=
# 全局默认置信度阈值（0-1）
AI_WATCH_MIN_CONFIDENCE=0.5

# /mp.ask 思考模式
AI_ASK_THINKING=true
# low | high | max
AI_ASK_REASONING_EFFORT=high
```

### 5. 启用插件

在 `pyproject.toml` 中确认：

```toml
[tool.nonebot]
plugins = ["materials_project"]
```

### 6. 准备别名字典

插件会自动扫描 `plugins/materials_project/` 下所有 `alias_dict*.json` 文件并合并：

- 从 release 下载 `alias_dict.json`，覆盖到插件目录（内置常见矿物与常见晶体的别名）
- 如需扩展其他语言或主题，把新文件命名为 `alias_dict_zh.json`、`alias_dict_en.json` 等放入同一目录即可
- 也可以手动创建空文件 `{}` 从零开始

### 7. 启动 bot

```bash
nb run
```

---

## 向仓库补充晶体名称词典

本仓库的 `alias_dict.json` 由社区共同维护，欢迎提交你自己的补充。流程如下：

1. **Fork** 本仓库到你的 GitHub 账户。
2. 在 `community/` 目录下新建一个 `.json` 文件，建议命名为 `<你的用户名>.json` 或 `<主题>.json`。
3. 按如下格式填写（键为别名，值为 mp ID 数组）：

   ```json
   {
     "萤石": ["mp-2741"],
     "金刚石": ["mp-66", "mp-47"]
   }
   ```

   格式要求：
   - 顶层必须是 JSON 对象
   - 每个键必须是非空字符串（别名）
   - 每个值必须是 mp ID 字符串数组
   - 同一别名可对应多个 mp ID；多个别名也可指向同一 mp ID

4. 提交 **Pull Request**。
5. GitHub Actions 会自动校验格式、将你的文件合并进根目录的 `alias_dict.json`，并把结果 commit 回 PR 分支。
6. 通过人工审核后，PR 合并进主分支，你的补充就会出现在下一次发布中。

> 根目录的 `alias_dict.json` 由 Actions 自动生成，**请勿手动编辑**。若只想在本地使用自定义字典，直接修改本地文件即可，无需提交。

---

## 详细功能介绍

### 功能一览

- **材料查询**：通过 `material_id` 获取对称化 CIF 文件
- **结构渲染**：调用 VESTA 渲染任意晶面投影或默认 (113) 视图
- **三视图**：`tri` 参数一次渲染 (100)、(010)、(001)
- **材料搜索**：支持「仅含元素」「至少含元素」「化学式」「别名」四种方式
- **分页浏览**：每页 10 条，支持 `nextp` / `lastp`
- **序号引用**：引用搜索结果序号获取 CIF 或渲染图
- **别名字典**：多对多映射，支持命令写入和手动编辑，多文件自动合并
- **AI 消息监听**：DeepSeek 分析群聊消息，识别晶体查询意图
- **AI 问答**：`/mp.ask` 支持晶体学与材料学问答，自动获取结构数据、按需渲染投影
- **对话记忆**：按群聊独立保存多轮问答，支持清除
- **冷却机制**：按群聊独立计时
- **群级配置**：启用/禁用、AI 监听、置信度阈值均可按群独立设置

### 指令总览

所有指令**仅在 bot 被 @ 时响应**（`nextp` / `lastp` 除外）。

#### 基本指令

| 指令 | 说明 |
|---|---|
| `/mp <material_id>` | 获取对称化 CIF 文件，如 `/mp mp-66` |
| `/mp.prev <material_id>` | 沿默认 (113) 晶面投影渲染 |
| `/mp.prev <material_id> <hkl>` | 沿指定晶面投影渲染，如 `/mp.prev mp-66 111` |
| `/mp.prev <material_id> tri` | 三视图，依次发送沿 (100)、(010)、(001) 的三张图片 |
| `/mp.help` | 显示指令索引 |

#### 搜索与引用

| 指令 | 说明 |
|---|---|
| `/mp.search <条件>` | 搜索材料，每页 10 条 |
| `nextp` / `lastp` | 翻页（无需 @，无需 `/`，无冷却） |
| `/mp.res <序号>` | 获取搜索结果中指定序号的 CIF |
| `/mp.res.prev <序号>` | 渲染指定序号的默认 (113) 视图 |
| `/mp.res.prev <序号> <hkl>` | 渲染指定序号的投影图 |
| `/mp.res.prev <序号> tri` | 渲染指定序号的三视图 |
| `/mp.res.CLR` | 清除本群搜索结果 |

**搜索条件自动匹配规则：**

| 输入示例 | 匹配方式 | 说明 |
|---|---|---|
| `Si-O` | 仅含元素 | 材料中只含 Si 和 O |
| `Si,O` | 至少含元素 | 材料中至少含 Si 和 O |
| `Fe2O3` | 化学式 | 按化学式精确匹配 |
| `萤石` | 别名 | 命中别名字典，返回其关联的所有 mp ID |

**搜索结果示例**（搜索 `金刚石`，返回字典中关联的 2 个条目）：

```
| 序号 | 是否测得 | mp ID | 化学式 | 空间群 | 原子数 |
| --- | --- | --- | --- | --- | --- |
| 1 | * | mp-66 | C | Fd-3m | 8 |
| 2 |   | mp-47 | C | P6_3/mmc | 4 |

第1页，共1页
```

> `是否测得` 列中的 `*` 表示实验测定的结构，空白表示理论预测。具体数值以实际查询结果为准。

#### 问答指令

| 指令 | 说明 |
|---|---|
| `/mp.ask <问题>` | 询问晶体学或材料学问题 |

- 若问题中未指明晶体，默认使用本群最近查询的晶体
- 若问题中明确提到 `mp-\d+`，使用该 mp ID
- 若问题中指定了与当前晶体不同的化学式或别名，会先搜索并询问用户选择
- 涉及对称元素位置的问题，会沿相应晶向渲染投影图（4 次轴 → 001；立方 3 次轴 → 111）
- **默认简短回答**（1–2 句）；问题含"详细""展开""详述"等词时展开解释

#### 别名字典

| 指令 | 说明 |
|---|---|
| `/mp.dict <别名> [mp ID]` | 关联别名与晶体；未指定 mp ID 时使用本群最近查询的晶体 |
| `/mp.dict.stats` | 查看当前加载的字典文件与统计信息 |

示例：

```
# 先查询一个晶体
@bot /mp.prev mp-66

# 关联别名
@bot /mp.dict 金刚石

# 也可显式指定 mp ID
@bot /mp.dict 石墨 mp-169
```

关联后，`/mp.search 金刚石` 会直接命中字典，返回 `mp-66` 和 `mp-47`。

#### 对话记忆

| 指令 | 说明 |
|---|---|
| `/mp.ai.CLR` | 清除本群 AI 对话记忆 |
| `/mp.ai.CLRALL` | 清除所有群的 AI 对话记忆 |

- 每群最多保留最近 **10 轮**问答
- AI 监听的路由环节读取最近 3 轮，`/mp.ask` 读取完整 10 轮
- 工具调用过程、错误消息**不会**写入记忆
- 保存在内存中，bot 重启后清空

#### 管理指令（不在 `/mp.help` 索引中）

| 指令 | 说明 |
|---|---|
| `/mp.SWT` | 切换本群插件启用/禁用状态（默认启用） |
| `/mp.CD` | 将本群所有冷却时间归零 |
| `/mp.WATCH` | 切换本群 AI 消息监听状态（默认关闭） |
| `/mp.ask.SWT` | 切换 `/mp.ask` 启用/禁用状态（默认启用） |
| `/mp.minconf <0-1>` | 设置本群 AI 监听置信度阈值；`reset` 恢复全局默认 |

### 冷却机制

| 指令 | 冷却机制 | 时长 |
|---|---|---|
| `/mp`、`/mp.prev` | 共用一个计时器 | 1 分钟 |
| `/mp.search` | 独立计时器 | 1 分钟 |
| `/mp.res`、`/mp.res.prev` | 滑动窗口，最多 3 次 | 1 分钟窗口 |
| `/mp.ask` | 不消耗冷却 | — |
| `nextp` / `lastp` | 无冷却 | — |
| AI 监听触发 | 不消耗冷却 | — |

- 冷却按群聊独立计算
- 冷却中提示

### AI 消息监听

开启 `/mp.WATCH` 后，插件监听群聊消息并交给 DeepSeek 分析：

| 群消息 | AI 处理 |
|---|---|
| `查金刚石的结构` | `/mp.search 金刚石` |
| `@bot 查萤石的结构` | `/mp.search 萤石` |
| `给出 7 号沿 122 晶面的投影` | `/mp.res.prev 7 122` + `/mp.res 7` |
| `查 12 号的结构` | `/mp.res.prev 12` + `/mp.res 12` |
| `mp-2741 属于什么晶系` | `/mp.ask mp-2741 属于什么晶系` |
| `记住锐钛矿就是 mp-390` | `/mp.dict 锐钛矿 mp-390` |

**通知机制**：AI 调用指令前，会先发送 `正在调用 /mp.search 金刚石` 形式的提示消息。

**触发过滤规则**（由 `AI_WATCH_SENSITIVITY` 控制）：

| 档位 | @bot 消息 | 非 @bot 消息 |
|---|---|---|
| `strict` | 需含关键词，≤200 字符 | 不处理 |
| `normal`（默认） | 直接处理，≤200 字符 | 需含关键词、≤100 字符；若群无查询上下文，还需含 `mp-\d+` |
| `loose` | 全处理 | ≤100 字符即处理 |

- 消息本身是 MP 指令（如 `@bot /mp.search 金刚石`）时跳过分析
- 空消息跳过

**置信度过滤**：AI 会为每次工具调用返回 `confidence`（0-1），低于当前群阈值的调用被丢弃。阈值通过 `/mp.minconf` 按群配置，未配置时使用 `AI_WATCH_MIN_CONFIDENCE` 全局默认值。

### AI 问答（`/mp.ask`）

`/mp.ask` 与 AI 监听配合：

- **直接提问**：`@bot /mp.ask 这个晶体属于什么晶系`
- **通过监听**：开启 `/mp.WATCH` 后，群里说 `mp-2741 属于什么晶系` 会自动触发

`/mp.ask` 在 DeepSeek 调用中启用思考模式（由 `AI_ASK_THINKING` 和 `AI_ASK_REASONING_EFFORT` 控制），而 AI 监听的路由环节不启用思考，以节省 token 并保持响应速度。

### 项目结构

```
materials_project/
├── __init__.py              # 插件入口，事件响应器注册
├── config.py                # 配置模型
├── mp_api.py                # MP API 封装、别名感知搜索
├── render_vesta.py          # VESTA 渲染与导出
├── search.py                # 搜索缓存与分页
├── cooldown.py              # 冷却计时器
├── admin.py                 # 群级启用/禁用状态
├── watch.py                 # 群级 AI 监听开关
├── ai_watcher.py            # DeepSeek 调用、工具定义、问答逻辑
├── ai_memory.py             # 群级对话记忆
├── alias_dict.py            # 别名字典多文件加载
├── alias_dict.json          # 主别名字典（/mp.dict 写入目标）
├── ask_context.py           # 群级「上一个查询的晶体」
├── ask_swt.py               # 群级 /mp.ask 开关
├── min_conf.py              # 群级置信度阈值
└── crystallography_skill.md # 供 AI 参考的晶体学知识
```

### 模块职责

| 模块 | 职责 |
|---|---|
| `mp_api.py` | `MPRester` 封装，含结构获取、CIF 生成、搜索、别名搜索、结构摘要 |
| `render_vesta.py` | 调用 VESTA 渲染，支持任意 (hkl) 投影与三视图 |
| `search.py` | 搜索缓存与分页格式化 |
| `cooldown.py` | 三类冷却计时器 |
| `admin.py` | 群级启用/禁用状态 |
| `watch.py` | 群级 AI 监听开关 |
| `ai_watcher.py` | DeepSeek 调用、工具定义、`analyze_message`、`ask_question` |
| `ai_memory.py` | 群级对话历史（10 轮上限） |
| `alias_dict.py` | 别名字典（多文件扫描、合并、mtime 热重载） |
| `ask_context.py` | 群级「上一个查询的晶体」 |
| `ask_swt.py` | 群级 `/mp.ask` 开关 |
| `min_conf.py` | 群级置信度阈值 |
| `crystallography_skill.md` | AI 参考的晶体学知识（插件内部使用，无需用户配置） |

---

## 关于 VESTA 渲染

### 命令行调用

```bash
VESTA -open structure.cif -export_img output.png -close
```

指定晶面投影时附加旋转参数：

```bash
VESTA -open structure.cif -rotate_x a -rotate_y b -export_img output.png -close
```

`a`、`b` 由 `(hkl)` 晶面法线方向通过反三角函数计算：

```python
lat = np.array(structure.lattice.matrix)
recip = np.linalg.inv(lat).T
normal = h * recip[:, 0] + k * recip[:, 1] + l * recip[:, 2]
vx, vy, vz = normal / np.linalg.norm(normal)

a = float(np.degrees(np.arctan2(vy, vz)))
v_z_after_x = float(np.sqrt(vy ** 2 + vz ** 2))
b = float(np.degrees(np.arctan2(-vx, v_z_after_x)))
```

### 默认视角与三视图

- **默认视角**：未指定 `hkl` 时，沿 (113) 晶面投影
- **三视图**：`hkl` 为 `tri` 时，依次渲染 (100)、(010)、(001) 并发送三张图

### 已知限制

- VESTA 的 `-export_img` 只导出图片，不会自动退出；插件检测到 PNG 生成后会主动终止进程
- VESTA 命令行只支持 `-rotate_x/y/z` 欧拉角；若 VESTA 的旋转约定（右手定则 / 施加顺序）与推导不一致，可能出现方向反向或轻微偏斜
- Linux 无头服务器需 `Xvfb`：

  ```bash
  xvfb-run -a /path/to/VESTA -open structure.cif -export_img output.png -close
  ```

  或在 `render_vesta.py` 的 `Popen` 参数前添加 `["xvfb-run", "-a"]`

---

## 获取 DeepSeek API Key

1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 注册并登录账号
3. 左侧菜单 **「API keys」** → 点击 **「创建 API KEY」**
4. 立即复制生成的 Key（形如 `sk-xxxxxxxx`）
5. 可能需要充值后使用（按 token 计费）

本插件使用标准 OpenAI 兼容接口调用 DeepSeek，**不需要任何 skill 文件**。`crystallography_skill.md` 是插件内部的晶体学参考资料，由插件在调用时读取并拼入 prompt，无需用户额外配置。

---

## 常见问题

<details>
<summary><b>插件加载时提示 <code>No module named 'mp_api'</code> / <code>'openai'</code></b></summary>

```bash
pip install mp-api pymatgen openai
```
</details>

<details>
<summary><b>渲染时提示 <code>VESTA executable not found</code></b></summary>

检查 `.env` 中 `VESTA_EXEC` 是否为正确的**绝对路径**，或确保 VESTA 已加入系统 `PATH`。
</details>

<details>
<summary><b>渲染时提示 <code>VESTA 进程超时被终止</code>，但图片已生成</b></summary>

正常现象。VESTA 导出图片后不会自动退出，插件在检测到图片生成后会主动终止进程。该警告可以忽略。
</details>

<details>
<summary><b>搜索返回空结果</b></summary>

1. 确认 `MP_API_KEY` 有效
2. 尝试更宽泛的条件（如 `Si-O` 改为 `Si,O`）
3. 若为别名搜索，用 `/mp.dict.stats` 确认字典已加载且包含该别名
4. 查看后台日志中的搜索参数和返回结果数量
</details>

<details>
<summary><b>字段报错 <code>invalid fields requested: ['is_experimental']</code></b></summary>

Materials Project API 已移除 `is_experimental`，改用 `theoretical`（`theoretical=False` 表示实验结构）。
</details>

<details>
<summary><b>冷却时没有任何输出</b></summary>

检查 `_check_enabled_and_cooldown` 是否接收 `bot` 参数并使用 `bot.send(event, ...)`，而非 `event.bot.send(...)`。`GroupMessageEvent` 没有 `.bot` 属性。
</details>

<details>
<summary><b>开启 <code>/mp.WATCH</code> 后 AI 监听无输出</b></summary>

按以下顺序排查：

1. 确认 `DEEPSEEK_API_KEY` 已配置，且**重启过 bot**
2. 确认群内发送过 `@bot /mp.WATCH`，且 bot 回复"开启 AI 消息监听了喵"
3. 检查消息是否符合触发过滤规则（`/mp.minconf` 可查看本群阈值；`AI_WATCH_SENSITIVITY` 控制过滤档位）
4. 在 `handle_ai_watch` 中临时加 `logger.info` 定位拦下消息的环节
</details>

<details>
<summary><b>AI 监听误触发 / 触发频率过高</b></summary>

- 用 `/mp.minconf 0.7`（或更高）提高本群置信度阈值
- 将 `AI_WATCH_SENSITIVITY` 调为 `strict`
- 关闭 `/mp.WATCH` 完全停止 AI 监听
</details>

<details>
<summary><b>AI 把别名翻译成化学式（如把"萤石"替换为"CaF2"），没走字典</b></summary>

插件会在 `analyze_message` 和 `ask_question` 中扫描别名字典，当消息包含已知别名时在 system prompt 中追加"必须原样传递"的提示。若仍不稳定，可在 `_dispatch_ai_call` 的 `mp_search` 分支加防绕过检查。
</details>

<details>
<summary><b><code>/mp.ask</code> 提示"还没进行搜索喵"或上下文丢失</b></summary>

- 上下文为空意味着本群尚未通过 `/mp`、`/mp.prev`、`/mp.res`、`/mp.res.prev` 获取过任何晶体
- 若问题中明确提到 `mp-\d+`，会直接使用该 ID，不依赖上下文
- `/mp.ai.CLR` 只清除 AI 对话记忆，不影响晶体上下文
</details>

<details>
<summary><b>别名字典手动编辑后没有立即生效</b></summary>

`alias_dict.py` 每次查询时检查所有字典文件的 mtime，发现变化会自动重新加载。若系统 mtime 精度为 1 秒，同一秒内的编辑可能延迟一秒生效。无需重启 bot。
</details>

<details>
<summary><b><code>/mp.res</code> / <code>/mp.res.prev</code> 提示"指令冷却中"</b></summary>

这两个指令共用一个滑动窗口：**从第一次调用起 1 分钟内最多 3 次**。第 4 次及以后会被拒绝，直到窗口过期。`/mp.CD` 可立即归零。
</details>

---

## 贡献

欢迎提交 Issue 和 PR。以下方向尤其欢迎：

- [ ] 精确 `[hkl]` 投影（预置 `.vesta` 模板）
- [ ] Linux + Xvfb 自动适配
- [ ] 支持更多渲染后端（ASE、py3Dmol）
- [ ] 支持按空间群、带隙、稳定性等条件筛选
- [ ] 支持多种 AI 后端（OpenRouter、Ollama 等）
- [ ] 对话记忆持久化（写入 JSON / SQLite）

晶体名称词典的贡献流程见上文「向仓库补充晶体名称词典」。

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 致谢

- [Materials Project](https://materialsproject.org/) —— 开放材料数据库与 API
- [NoneBot2](https://github.com/nonebot/nonebot2) —— 异步 Python 机器人框架
- [VESTA](https://jp-minerals.org/vesta/) —— 晶体结构可视化工具
- [pymatgen](https://pymatgen.org/) —— 材料科学 Python 工具库
- [DeepSeek](https://platform.deepseek.com/) —— 兼容 OpenAI 接口的推理服务

---

## 免责声明

本插件仅供学习和科研使用。使用 Materials Project API 时请遵守其[使用条款](https://materialsproject.org/terms-of-use)，使用 DeepSeek API 时请遵守其平台服务条款。