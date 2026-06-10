<div align="center">
<img src="icon.svg" width="96" alt="WadwaitaUp icon" />

# WadwaitaUp

**一个 Adwaita 风格的课程表管理应用**

A sleek, Libadwaita-themed course schedule manager for university students.

[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-blue)](https://github.com/Nakanomk/WadwaitaUp)
[![GTK](https://img.shields.io/badge/GTK-4.0-%23ff7800)](https://www.gtk.org/)
[![Libadwaita](https://img.shields.io/badge/Libadwaita-1.x-%233584e4)](https://gnome.pages.gitlab.gnome.org/libadwaita/)
[![Python](https://img.shields.io/badge/python-3.10%2B-%2333d17a)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-%239141ac)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.1.0-%23e5a50a)](VERSION)

</div>

---

## ✨ 功能 · Features

**📋 多课表管理**
为不同学期创建独立课表，一键切换。学期开始日期、总周数均可自定义。

**📚 三种视图**

- **概览** — 今日课程提醒、下一节课倒计时、学期进度，以及「吉祥物卡片」智能问候
- **周视图** — 7 列网格，课程卡片颜色标识，自动检测时间冲突，支持跨周导航
- **月视图** — 日历热力图，每天课程一目了然

**📥 灵活导入**

- **iCalendar (`.ics`)** — 从教务系统导出的日历文件直接导入，支持 `RRULE` 循环规则
- **JSON** — 批量导入，支持单时段和多时段两种格式，可使用节次编号代替具体时间
- 导入时自动检测同名课程冲突，支持跳过或覆盖

**📤 导出到系统日历**
一键导出为 `.ics` 文件。连续周次和单/双周课程自动生成 `RRULE` 循环规则，文件精简高效。

**⏰ 智能提醒**
吉祥物根据当前时间给出不同问候（早上好/午安/下午好/晚上好/夜深了），并在课程即将开始时提醒你。

**🎨 深度 Libadwaita 集成**

- 自动跟随系统深色/浅色模式
- `Adw.ViewSwitcher` 视图切换
- `Adw.AboutDialog` 关于对话框
- `Adw.MessageDialog` 系统提示
- `Adw.PreferencesGroup` / `Adw.ActionRow` 设置布局
- 完整 CSS 自定义：课程卡片、吉祥物卡片、月历、引导页

**🔧 高级功能**
- **时间方案（令时）** — 配置夏令时/冬令时节次表，按日期自动切换
- **节次快选** — 添加课程时从预设节次快速填充时间
- **冲突检测** — 自动标出时间重叠的课程
- **周次解析** — 支持 `1-16`、`1,3,5`、`单`/`奇`、`双`/`偶` 等多种周次写法
- **学期进度** — 根据当前日期自动计算所在周数
- **新手引导** — 首次启动的四步引导页

---

## 📸 预览 · Screenshots

> *Screenshots coming soon — PRs welcome!*

---

## 🚀 安装 · Installation

### 依赖项 · Dependencies

WadwaitaUp 仅需 **GTK4**、**Libadwaita** 和 **PyGObject**（Python GObject 绑定）。

### 一键安装

```bash
bash install.sh
```

### 手动安装

<details>
<summary><b>🐧 Arch Linux</b></summary>

```bash
sudo pacman -Syu --needed python python-gobject gtk4 libadwaita
```
</details>

<details>
<summary><b>🐧 Fedora</b></summary>

```bash
sudo dnf install -y python3-gobject gtk4 libadwaita
```
</details>

<details>
<summary><b>🐧 Debian / Ubuntu</b></summary>

```bash
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```
</details>

<details>
<summary><b>🍎 macOS (Homebrew)</b></summary>

```bash
brew install pygobject3 gtk4 libadwaita
```
</details>

<details>
<summary><b>🪟 Windows (MSYS2)</b></summary>

在 **MINGW64** 终端中运行：

```bash
pacman -S mingw-w64-x86_64-python-gobject \
          mingw-w64-x86_64-gtk4 \
          mingw-w64-x86_64-libadwaita
```
</details>

### 运行

```bash
python main.py
```

或赋予执行权限后直接运行：

```bash
chmod +x main.py
./main.py
```

---

## 📖 使用指南 · User Guide

### 🗂️ 课表管理

1. 点击右上角 **📁 新建课表** 按钮
2. 输入课表名称（如「2024-2025 秋季学期」）、学期开始日期、总周数
3. 点击 **保存**

你可以在顶栏中央的下拉菜单中切换课表，或点击 **✏️ 编辑课表** 修改当前课表信息。点击 **🗑️ 删除课表** 可移除无需的课表（至少保留一个）。

### ➕ 添加课程

点击右上角 **＋** 按钮：

- **课程名**（必填）
- **星期** — 周一到周日
- **开始/结束节次** — 从预设节次表中选择，或选「自定义」手动输入时间
- **开始/结束时间** — `HH:MM` 格式
- **地点**、**教师**（可选）
- **周次** — 如 `1-16`、`1,3,5`、`单`/`双`，留空则不限制

### 📥 导入课程

支持三种导入方式：

#### 1. iCalendar 文件（`.ics`）

从教务系统导出的日历文件。自动识别 `DTSTART`/`DTEND`/`SUMMARY`/`LOCATION`/`DESCRIPTION`/`RRULE` 等字段，同名课程自动去重。

#### 2. JSON 文件 / 粘贴

点击 **导入课程** → **选择文件…** 或直接粘贴 JSON 到文本框 → **解析预览** → **导入**。

<details>
<summary><b>📋 JSON 格式说明</b></summary>

#### 单时段格式（兼容旧版）

```json
[
  {
    "name": "高等数学",
    "day": 1,
    "start": "08:00",
    "end": "09:40",
    "location": "东1-101",
    "teacher": "张老师",
    "weeks": "1-16"
  }
]
```

#### 多时段格式（一门课多个上课时间）

```json
[
  {
    "name": "英语",
    "location": "北1-310",
    "teacher": "王老师",
    "weeks": "1-16",
    "sessions": [
      {"day": 2, "start": "10:10", "end": "11:50"},
      {"day": 4, "start_period": 5, "end_period": 6}
    ]
  }
]
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | **必填**。课程名称 |
| `day` | int / string | 星期。`1`–`7` 或 `"周一"`/`"MO"` 等 |
| `start` / `end` | string | `HH:MM` 时间，如 `"08:00"` |
| `start_period` / `end_period` | int | 节次编号（需事先在设置中配置节次时间表） |
| `location` | string | 上课地点 |
| `teacher` | string | 教师姓名 |
| `weeks` | string | 周次范围。`"1-16"`、`"1,3,5"`、`"单"`、`"双"` 等 |

**⚠️ 注意：** 节次编号方式（`start_period`/`end_period`）需要先在「全局设置 → 节次时间」或「时间方案」中配置节次表，否则导入会失败。

</details>

#### 3. 从 HUST 教务系统导入

1. 访问 [HUST 教务系统课表页面](https://hubs.hust.edu.cn/basicInformation/scheduleInformation/index)
2. 点击 **「总课表」** 按钮
3. 按 `F12` 打开开发者工具，找到 `<div class="el-row">` 标签，复制其下全部内容
4. 将内容粘贴给 LLM，并附上本程序的 JSON 格式说明，请 LLM 生成对应的 JSON
5. 将生成的 JSON 粘贴到程序的导入对话框中

### 📤 导出到日历

点击 **📅 导出课程表** 按钮，选择保存路径即可生成 `.ics` 文件。可以导入到 Google Calendar、Apple Calendar、Outlook 等任意日历应用。

> 导出会自动使用 `RRULE` 循环规则（连续周次和单/双周课程），日历应用不会出现大量重复事件。

### 🎨 外观设置

点击 **⚙️ 全局设置**：

- **深色模式** — 切换深色/浅色主题（也可在顶栏右侧快速切换）
- **节次时间** — 自定义每节课的起止时间，提供 HUST 夏令时/冬令时预设
- **时间方案（令时）** — 创建多个节次表并设定各自生效的日期范围（MM-DD → MM-DD），系统根据当前日期自动选择

---

## 📁 项目结构 · Project Structure

```
WadwaitaUp/
├── main.py          # 入口 — GTK 初始化、版本加载、应用启动
├── window.py        # 主窗口 + 所有对话框 + 周/月视图组件
├── models.py        # 数据模型 — Course, ClassPeriod, TimeScheme, Schedule
├── utils.py         # 工具函数 — 周次解析、冲突检测、ICS 导出、时间计算
├── importer.py      # 导入器 — iCalendar (.ics) 和 JSON 解析
├── storage.py       # 持久化 — JSON 文件存储（原子写入）
├── install.sh       # 跨平台依赖安装脚本
├── VERSION          # 语义化版本号
└── data/            # 用户数据目录（自动创建）
    ├── schedules.json
    └── settings.json
```

---

## 🛠️ 技术栈 · Tech Stack

| 层 | 技术 |
|---|------|
| **UI 框架** | GTK 4 + Libadwaita 1.x |
| **语言绑定** | PyGObject (Python GObject Introspection) |
| **数据存储** | JSON（原子写入保证数据安全） |
| **日历标准** | iCalendar RFC 5545（导入 + 导出，含 RRULE 支持） |
| **目标平台** | Linux / macOS / Windows (MSYS2) |

---

## 🤝 贡献 · Contributing

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证 · License

MIT © [Nakanomk](https://github.com/Nakanomk)

---

<div align="center">

**Made with ❤️ for HUST students — and university students everywhere.**

</div>
