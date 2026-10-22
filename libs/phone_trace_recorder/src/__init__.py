"""手机轨迹录制器 —— 源码包。

模块划分:
- adb_utils : adb 封装(设备列表、屏幕信息、触摸输入设备探测)
- recorder  : 录制引擎(getevent 流解析为手势序列)
- storage   : 记录存储(recordings/ 目录,JSON 文件)
- exporter  : 导出可独立运行的 .py 回放脚本(标准 / root 两种模式)
- player    : 应用内回放(复用导出脚本,行为一致)
- ui_main   : CustomTkinter 主界面
"""
