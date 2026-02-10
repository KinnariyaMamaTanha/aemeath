# Aemeath — 爱弥斯桌宠 🦭

一个轻量级、跨平台[^1]的桌面宠物应用。鸣潮角色**爱弥斯**（Aemeath）会跟随你的鼠标在桌面上活动，展现出丰富的行为和可爱的动画。

![Python](https://img.shields.io/badge/Python-≥3.10-blue)
![Qt](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20|%20Linux-lightgrey)

![](./assets/banner.jpg)

---

## ✨ 特性

- **跟随鼠标** — 爱弥斯会追逐你的光标，到达后在附近随机游荡，然后停下来播放各种待机动画
- **丰富行为** — 追逐、游荡、待机、拖拽、海豹互动等多种状态自然切换
- **海豹彩蛋** — 长时间不动鼠标后，一只小海豹会出现在屏幕随机位置，爱弥斯会跑过去和它互动 🦭
- **屏幕自适应** — 角色大小、移动速度和距离阈值根据屏幕分辨率自动缩放，切换显示器时实时适配
- **轻量高效** — 纯 Python + Qt，内存占用极小，不影响日常使用
- **跨平台** — 支持 Windows 和 Linux（X11 / Wayland）
- **系统托盘** — 可通过托盘图标退出程序

## 🎬 行为逻辑

| 条件 | 行为 | 动画 |
|------|------|------|
| 鼠标距离较远 | 向鼠标奔跑 | `move.gif`（根据方向自动翻转） |
| 鼠标距离较近 | 在鼠标附近随机游荡 | `move.gif` |
| 游荡一段时间后 | 停下播放待机动画 | 随机选择 `idle1~5.gif` |
| 鼠标静止超过 30s | `idle2.gif` 出现概率逐渐增加至 100% | `idle2.gif` |
| 鼠标静止超过 120s | 海豹出现，爱弥斯跟随海豹互动 | `seal.gif` + `move.gif` |
| 鼠标正在拖拽/选择 | 播放拖拽动画 | `drag.gif` |

## 📦 安装

### 前置要求

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）或 pip

### 使用 uv（推荐）

```bash
git clone https://github.com/KinnariyaMamaTanha/aemeath.git
cd aemeath
uv sync
```

### 使用 pip

```bash
git clone https://github.com/KinnariyaMamaTanha/aemeath.git
cd aemeath
pip install .
```

## 🚀 运行

```bash
# 使用 uv
uv run aemeath

# 或安装后直接运行
aemeath
```

启动后爱弥斯会出现在屏幕上，系统托盘会显示图标。右键托盘图标即可退出。

## 📦 构建为独立可执行文件

无需 Python 环境即可运行的单文件可执行程序。构建配置已做跨平台适配，支持 Linux 和 Windows。

### 方式一：使用 Nuitka（推荐）⚡

Nuitka 将 Python 编译为 C 代码，生成原生执行文件，具有更快的速度和更小的体积。

```bash
uv sync --dev
uv run python build_nuitka.py
```

### 方式二：使用 PyInstaller

```bash
uv sync --dev
uv run pyinstaller aemeath.spec --clean
```

> **注意**：两种方式均无法交叉编译，必须在目标操作系统上执行构建。

## ⚙️ 配置

所有可调参数均定义在 `src/aemeath/config.py` 中，可按需修改：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MOVE_SPEED` | 4.0 | 追逐鼠标时的移动速度（像素/帧） |
| `WANDER_SPEED` | 1.5 | 游荡时的移动速度（像素/帧） |
| `NEAR_DISTANCE` | 80.0 | 判定"鼠标附近"的距离阈值 |
| `FAR_DISTANCE` | 250.0 | 判定"鼠标较远"的距离阈值 |
| `MOUSE_IDLE_T1` | 30s | 鼠标静止多久后 idle2 概率开始上升 |
| `MOUSE_IDLE_T2` | 120s | 鼠标静止多久后海豹出现 |
| `SPRITE_SCALE` | 0.35 | GIF 基准缩放比例（会按屏幕高度自适应） |
| `REFERENCE_SCREEN_HEIGHT` | 1280 | 基准缩放参照的屏幕高度（像素） |
| `TICK_INTERVAL` | 33ms | 游戏循环间隔（≈30 FPS） |

## 🏗️ 项目结构

```
aemeath/
├── assets/
│   ├── gifs/          # 动画 GIF 文件
│   │   ├── move.gif       # 移动/奔跑
│   │   ├── drag.gif       # 拖拽状态
│   │   ├── seal.gif       # 海豹
│   │   └── idle1~5.gif    # 待机动画
│   └── icons/
│       └── aemeath.ico    # 托盘图标
├── src/aemeath/
│   ├── app.py         # 主应用控制器、系统托盘、游戏循环
│   ├── config.py      # 所有可调常量
│   ├── cursor.py      # 多后端光标位置追踪
│   ├── pet.py         # 纯逻辑状态机（无 Qt 依赖）
│   └── sprite.py      # 透明无边框 GIF 动画窗口
└── pyproject.toml
```

## 🖥️ 平台支持

| 平台 | 状态 | 光标追踪方式 |
|------|------|-------------|
| Windows | ✅ | Win32 API (`GetCursorPos`) |
| Linux X11 | ✅ | XQueryPointer via ctypes |
| Linux Wayland + KDE | ✅ | KWin 脚本 + D-Bus |
| Linux Wayland + Hyprland | ✅ | `hyprctl cursorpos` |
| Linux Wayland + GNOME | ✅ | libinput 事件 |
| Linux Wayland (其他) | ⚠️ | 混合模式（XWayland 回退） |

## 📄 许可证

MIT License

[^1]: 按道理是这样的，但是受限于本人机器，仅在 fedora 下的 kde 桌面环境进行了测试