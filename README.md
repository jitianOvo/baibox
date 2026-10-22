# 超级白工具箱 · baibox

`baibox` 取“白”的拼音加 `box`，软件中文名保留“超级白工具箱”。项目仓库：[jitianOvo/baibox](https://github.com/jitianOvo/baibox)。

Windows 桌面工具箱，主界面使用 PySide6。包含 Android／ADB、文件处理、软件中心、数据备份、视频压缩，以及小说、音乐、视频整合入口「听读看」。

## 启动与资料

使用本机安装了项目依赖的 Python 运行：

```powershell
python MainGUI.py
```

本阶段在 Windows、Python 3.13 环境检查；主要依赖 PySide6、requests、PyExecJS，以及各功能模块的现有依赖。听读看额外依赖与使用方法见 [听读看说明](libs/media_hub/README.md)；JavaScript 音源需要 Node.js，视频合并复用现有 FFmpeg 核心。

- [2026-10-22 阶段归档说明](docs/ARCHIVE-2026-10-22.md)
- [听读看使用与维护](libs/media_hub/README.md)
- [更新记录](data/update_logs.txt)
- [维护笔记](docs/notes/)

## 本地配置与缓存

智能助手密钥通过环境变量 `SILICONFLOW_API_KEY` 或本机 `data/local/ai_assistant.json` 的 `api_key` 字段提供。密钥、阅读记录、下载内容与录制记录均不进入 Git。

项目缓存清理默认只预览，实际清理需显式加 `--apply`：

```powershell
python scripts/clean_project_cache.py
python scripts/clean_project_cache.py --apply
```

源码、初始源配置、正式资源和配套工具保留在仓库内。个人使用状态及完整恢复资料保存在本机 `.archive/`，迁移电脑时另行复制。

## 阶段验证

2026-10-22：60 个 Python 文件语法检查、40 项听读看检查，以及清理范围保护和智能助手本机密钥读取检查通过。本次保存开发状态，不生成或发布安装包。

```powershell
python -m unittest discover -s tests -p test_media_hub.py -v
```

项目许可证见 [LICENSE](LICENSE)，第三方配套程序及资源沿用其各自许可。
