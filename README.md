# baibox

**超级白工具箱 · Windows & Android Toolkit**

面向 Windows 与 Android 的桌面工具箱，将设备管理、文件处理、数据备份与多媒体工具整合在同一个工作台。基于 Python 与 PySide6 构建，常用操作集中呈现，独立功能按需加载。

## 功能

| 模块 | 主要能力 |
| --- | --- |
| 设备管理 | ADB／Fastboot 操作、无线连接、Scrcpy 投屏、手机操作轨迹录制 |
| 文件与数据 | 文件搜索、分割与合并、重复文件识别、电脑与手机数据备份 |
| 系统工具 | 软件检索与安装、缓存管理、残留清理、常用系统设置 |
| 视频处理 | 视频压缩、手机视频处理、FFmpeg 核心组件管理 |
| 听读看 | 小说阅读与章节下载、跨平台音乐搜索、视频播放与下载、资源管理 |

听读看支持全屏阅读、阅读样式调整、播放线路切换与清晰度选择。详细用法见[听读看使用指南](libs/media_hub/README.md)。

## 快速开始

### 环境

- Windows 10／11
- Python 3.11 或更新版本
- 音乐自定义源：Node.js 22.13 或更新版本
- 视频压缩与 HLS 合并：FFmpeg，可复用工具箱已有核心组件

### 从源码运行

```powershell
git clone https://github.com/jitianOvo/baibox.git
cd baibox
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install PySide6 requests PyExecJS customtkinter -r libs/media_hub/requirements.txt
.\.venv\Scripts\python.exe MainGUI.py
```

Android 设备功能需要开启 USB 调试并完成设备授权。首次使用无线连接时，按界面提示完成配对或连接。

## 使用与配置

主界面按设备操作、系统工具与其他功能分区。进入「其他 → 听读看 · 资源小站」可使用阅读、音乐和视频功能；自定义资源配置位于「设置 → 高级维护」。

智能助手使用独立的 API 密钥，可通过环境变量配置：

```powershell
$env:SILICONFLOW_API_KEY = "你的 API 密钥"
python MainGUI.py
```

阅读进度、源配置和下载记录保存在本机。源配置支持导入、导出和备份，资源可用性随上游服务变化。

## 项目结构

```text
baibox/
├── MainGUI.py          # 桌面入口
├── core_function.py    # 通用工具功能
├── core_lib.py         # 公共资源与文件处理
├── libs/               # 独立功能模块
├── assets/             # 界面资源与初始配置
├── tools/              # 配套工具
└── data/               # 更新信息与本机运行数据
```

## 反馈

遇到问题或希望增加功能，可提交 [Issue](https://github.com/jitianOvo/baibox/issues)。反馈时请附上系统版本、相关功能、复现步骤与错误信息。

## 许可证

项目源码采用 [Apache License 2.0](LICENSE)。第三方工具、字体和资源保留各自的许可证与使用条件。
