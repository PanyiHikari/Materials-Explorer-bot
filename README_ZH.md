[English](README.md)

# Materials Project Bot

一个基于 [NoneBot2](https://github.com/nonebot/nonebot2) 的 QQ 机器人插件，接入 [Materials Project](https://materialsproject.org/) API，在群聊中查询晶体结构、搜索材料、获取 CIF 文件，并通过 [VESTA](https://jp-minerals.org/vesta/) 渲染晶体结构图片。

---

## 功能特性

- **材料查询**：通过 `material_id`（如 `mp-162`）获取对称化 CIF 文件
- **结构渲染**：调用 VESTA 渲染晶体结构的默认视图或指定晶面投影图
- **材料搜索**：支持按「仅含元素」「至少含元素」「化学式」三种模式自动匹配搜索
- **分页浏览**：搜索结果按每页 10 条展示，支持 `nextp` / `lastp` 翻页
- **序号引用**：直接引用搜索结果中的序号获取 CIF 或渲染图片
- **冷却机制**：按群聊独立计时，防止滥用
- **管理指令**：支持群级开关和冷却重置

---

## 安装

### 1. 安装 NoneBot2 与适配器

如果你还没有 NoneBot2 项目，请先参考[官方文档](https://nonebot.dev/docs/quick-start)创建一个：

```bash
pip install nonebot2 nonebot-adapter-onebot
```

### 2. 安装插件依赖

```bash
pip install mp-api pymatgen
```

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
│       └── admin.py
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
```

配置字段会自动映射到 `config.py` 中的 `Config` 模型（NoneBot2 会自动把环境变量转为小写字段名）。

---

## 使用方法

所有指令**仅在 bot 被 @ 时响应**（`nextp` / `lastp` 除外）。

### 基本指令

| 指令 | 说明 |
|---|---|
| `/mp <material_id>` | 获取指定材料的对称化 CIF 文件 |
| `/mp.prev <material_id>` | 渲染默认视图下的晶体结构图片 |
| `/mp.prev <material_id> <view>` | 沿指定晶面（如 `011`、`111`）投影渲染 |
| `/mp.help` | 显示指令索引 |

### 搜索与引用

| 指令 | 说明 |
|---|---|
| `/mp.search <条件>` | 搜索材料，每页 10 条 |
| `nextp` / `lastp` | 翻页（无需 @，无需 `/`，无冷却） |
| `/mp.res <序号>` | 获取搜索结果中指定序号的 CIF |
| `/mp.res.prev <序号>` | 渲染搜索结果中指定序号的默认视图 |
| `/mp.res.prev <序号> <view>` | 渲染搜索结果中指定序号的投影图 |
| `/mp.res.CLR` | 清除本群搜索结果 |

**搜索条件自动匹配规则：**

| 输入示例 | 匹配模式 | 说明 |
|---|---|---|
| `Si-O` | 仅含元素 | 材料中只含 Si 和 O |
| `Li-Fe-P-O` | 仅含元素 | 材料中只含 Li、Fe、P、O |
| `Si,O` | 至少含元素 | 材料中至少含 Si 和 O |
| `Fe,Co,Ni` | 至少含元素 | 材料中至少含 Fe、Co、Ni |
| `Fe2O3` | 化学式 | 按化学式精确匹配 |

### 管理指令（不在 `/mp.help` 索引中）

| 指令 | 说明 |
|---|---|
| `/mp.SWT` | 切换本群插件启用/禁用状态（默认启用） |
| `/mp.CD` | 将本群所有冷却时间归零 |

### 冷却机制

- `/mp`、`/mp.prev` **共用**一个冷却计时器，时长 **2 分钟**
- `/mp.search` 单独计时，时长 **2 分钟**
- 冷却时间**按群聊独立计算**
- 翻页指令 `nextp` / `lastp` **无冷却**

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
└── admin.py           # 群级启用/禁用状态管理
```

### 模块职责

| 模块 | 职责 |
|---|---|
| `mp_api.py` | 封装 `MPRester`，提供获取结构、生成 CIF、搜索材料等异步接口 |
| `render_vesta.py` | 调用 VESTA 命令行渲染 CIF 并导出 PNG，支持默认视图与晶面投影 |
| `search.py` | 维护每个群聊的搜索缓存，处理分页格式化 |
| `cooldown.py` | 维护每个群聊的两类冷却计时器 |
| `admin.py` | 维护每个群聊的启用状态 |

---

## 关于 VESTA 渲染

### 命令行调用方式

插件通过如下命令行参数调用 VESTA：

```bash
VESTA -open structure.cif -export_img output.png -close
```

指定晶面投影时附加旋转参数：

```bash
VESTA -open structure.cif -rotate_x 30 -rotate_y 45 -export_img output.png -close
```

### 已知限制

- VESTA 的 `-export_img` 参数只负责导出图片，**不会让程序自动退出**，因此插件在检测到 PNG 生成后会**主动终止 VESTA 进程**。
- VESTA 命令行只暴露 `-rotate_x/y/z` 欧拉角参数，**无法直接指定 `[hkl]` 法线方向**。插件中沿晶面投影采用的是启发式近似旋转，精确对齐需要预置 `.vesta` 模板文件（暂未实现）。
- Linux 无头服务器需要 `Xvfb` 虚拟显示：

  ```bash
  xvfb-run -a /path/to/VESTA -open structure.cif -export_img output.png -close
  ```

  或在 `render_vesta.py` 的 `Popen` 参数前加上 `["xvfb-run", "-a"]`。

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

---

## 贡献

欢迎提交 Issue 和 PR。如果你实现了以下功能，非常欢迎分享：

- [ ] 精确 `[hkl]` 投影（通过预置 `.vesta` 模板）
- [ ] Linux + Xvfb 的自动适配
- [ ] 支持更多渲染后端（如 ASE、py3Dmol）
- [ ] 支持按空间群、带隙、稳定性等条件筛选

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 致谢

- [Materials Project](https://materialsproject.org/) —— 提供开放的材料数据库与 API
- [NoneBot2](https://github.com/nonebot/nonebot2) —— 优秀的 Python 异步机器人框架
- [VESTA](https://jp-minerals.org/vesta/) —— 强大的晶体结构可视化工具
- [pymatgen](https://pymatgen.org/) —— 材料科学 Python 工具库

---

## 免责声明

本插件仅供学习和科研使用。使用 Materials Project API 时请遵守其[使用条款](https://materialsproject.org/terms-of-use)。