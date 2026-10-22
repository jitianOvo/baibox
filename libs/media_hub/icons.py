from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from core_lib import get_path

INK = '#526581'
FOLDER = Path(get_path('assets/media_hub/icons'))

ACTION_ICONS = {
    '打开链接': 'link', '最近使用': 'history', '设置': 'settings',
    '搜索': 'search', '下一页': 'next', '播放／暂停': 'play', '播放/暂停': 'play',
    '停止': 'stop', '换源': 'switch', '取消任务': 'close', '详情': 'info',
    '上一章': 'previous', '上一集': 'previous', '下一章': 'next', '下一集': 'next',
    '打开选中': 'play', '保存正文': 'save', '下载': 'download',
    '下载单章': 'save', '下载全本': 'download', '开始下载': 'download',
    '下载全本／区间…': 'download', '全屏阅读': 'fullscreen', '阅读设置': 'settings', '取消': 'close',
    '全屏': 'fullscreen', '退出全屏': 'collapse', '字号＋': 'font-plus', '字号－': 'font-minus',
    '更多': 'more', '打开原网页': 'web', '网页播放': 'video',
    '导入文件': 'import', '导入网址': 'link', '粘贴配置': 'paste', '网址订阅': 'refresh',
    '刷新全部订阅': 'refresh', '管理／移除订阅': 'settings', '移除选中的订阅': 'delete',
    '恢复备份': 'backup', '检测选中': 'check', '启用／恢复': 'enable', '停用': 'disable',
    '清理失效': 'clean', '编辑': 'edit', '导出备份': 'export', '导出原始': 'export',
    '存储目录': 'folder', '高级维护…': 'settings', '关闭': 'close', '保存': 'save',
    '复制': 'copy', '复制链接地址': 'link', '粘贴': 'paste', '剪切': 'cut',
    '撤销': 'undo', '重做': 'redo', '删除': 'delete', '全选': 'select-all',
    '重新加载': 'refresh', '静音／取消静音': 'mute', '使用检测到的媒体链接': 'link',
}


def icon(name, color=INK):
    app = QApplication.instance()
    if not hasattr(app, '_media_hub_icons'):
        app._media_hub_icons = {}
    key = (name, color)
    if key not in app._media_hub_icons:
        path = FOLDER / (name + '.svg')
        if color == INK:
            result = QIcon(str(path))
        else:
            svg = path.read_text(encoding='utf-8').replace(INK, color)
            renderer = QSvgRenderer(QByteArray(svg.encode()))
            result = QIcon()
            for size in (18, 24, 32, 48, 64):
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                result.addPixmap(pixmap)
        app._media_hub_icons[key] = result
    return QIcon(app._media_hub_icons[key])


def action_icon(text, color=INK):
    return icon(ACTION_ICONS.get(text, 'settings'), color)
