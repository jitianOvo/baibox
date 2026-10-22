"""应用常量定义：版本、预设、扩展名、缓存目录、编码后缀映射。"""

from pathlib import Path

APP_NAME = "大丸工具箱"
APP_VERSION = "V3"
APP_USER_MODEL_ID = "dwgjx"
CONTACT_QQ = "2097004227"

# 视频扩展名白名单
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mts", ".m2ts", ".3gp", ".mpeg", ".mpg",
}

# 文件选择对话框的过滤器
VIDEO_FILE_FILTER = (
    "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm "
    "*.m4v *.ts *.mts *.m2ts *.3gp *.mpeg *.mpg);;所有文件 (*.*)"
)

# 缓存目录：C:\Users\用户名\Pyffmpeg
CONFIG_DIR = Path.home() / "Pyffmpeg"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 各编码方案输出文件名后缀，避免覆盖原视频
# 形如 video.mp4 -> video_av.mp4 / video_x265.mp4 / video_hv.mp4
ENCODER_SUFFIX = {
    "av1": "_av",
    "x265": "_x265",
    "nvenc_h265": "_hv",
}

# 压缩预设：name 显示文本，encoder 调度键，params ffmpeg 参数
PRESETS = [
    {
        "name": "预设1：AV1 NVENC（p3, cq41）",
        "encoder": "av1",
        "params": {"cq": 41, "preset": "p3"},
        "desc": "AV1 NVENC（日常推荐，GPU）。适合手机录像、日常视频压缩。"
                "新款 NVIDIA 显卡可用。体积接近小丸工具箱，速度约快 2.8 倍，画质更好。",
    },
    {
        "name": "预设2：AV1 NVENC_LOW（p3, cq50）",
        "encoder": "av1",
        "params": {"cq": 50, "preset": "p3"},
        "desc": "AV1 NVENC_LOW（极限快速压缩，GPU）。适合追求更小体积的批量压缩。"
                "体积可比 CPU x265 更小，速度约快 2.8 倍；细节会略微变糊。",
    },
    {
        "name": "预设3：CPU x265（libx265, crf28）",
        "encoder": "x265",
        "params": {"crf": 28, "preset": "slow"},
        "desc": "CPU x265（极限压缩，CPU）。适合单个文件追求体积和质量平衡。"
                "体积通常比小丸工具箱小一半，但耗时约慢 2 倍。",
    },
    {
        "name": "预设4：HEVC NVENC_HIGH（cq28, p5）",
        "encoder": "nvenc_h265",
        "params": {"cq": 28, "preset": "p5"},
        "desc": "HEVC NVENC_HIGH（高质量普通压缩，GPU）。适合老款 NVIDIA 显卡或更看重画质。"
                "体积会比小丸工具箱大一些，速度约快 2 倍，画质更好。",
    },
    {
        "name": "预设5：HEVC NVENC_LOW（cq34, p5）",
        "encoder": "nvenc_h265",
        "params": {"cq": 34, "preset": "p5"},
        "desc": "HEVC NVENC_LOW（网课批量压缩，GPU）。适合批量网课、录屏等内容，是次选推荐。"
                "体积接近小丸工具箱，速度约快 2.8 倍，画质相近。",
    },
]

# ffmpeg 子进程使用的输出格式后缀
OUTPUT_SUFFIX = "mp4"

# 大丸工具箱压缩标识：写入视频元数据，用于识别已压缩文件并跳过
DWGJX_MARK = "CompressedByDwgjx"
DWGJX_MARK_KEY = "comment"
