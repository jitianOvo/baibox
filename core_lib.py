import ctypes
import os
import sys
import math

def ctypes_appid(IDname='®JT.jitian.v2.0'):
    """为tk、pyqt5提供任务栏图标正常显示"""
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(IDname)

def get_path(relative_path):
    """获取资源文件的绝对路径，兼容 PyInstaller 打包后"""
    if getattr(sys, 'frozen', False):
        # 如果是 PyInstaller 打包后的 exe，资源会被放在临时目录 sys._MEIPASS
        base_path = sys._MEIPASS
    else:
        # 正常运行时，文件就在当前脚本目录下
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def split_file(file_path, output_dir):
    """分片保存为 .txt，序号在前，并在每个分片开头保存原文件名和扩展名"""
    CHUNK_SIZE = int(99.99 * 1024 * 1024)  # 99.99 MB
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    file_name = os.path.basename(file_path)
    file_ext = os.path.splitext(file_name)[1]  # 含点的后缀，如 ".mp4"
    file_size = os.path.getsize(file_path)
    total_parts = math.ceil(file_size / CHUNK_SIZE)
    with open(file_path, 'rb') as f:
        for part_num in range(total_parts):
            chunk_data = f.read(CHUNK_SIZE)
            part_filename = os.path.join(output_dir, f"{part_num + 1:04d}.txt")
            with open(part_filename, 'wb') as pf:
                # 在文件最前面写入原始文件名信息（UTF-8），然后一个换行
                header = f"{file_name}\n".encode('utf-8')
                pf.write(header)
                pf.write(chunk_data)
            print(f"生成分片: {part_filename}")
    print(f"分片完成，共 {total_parts} 片")

def merge_file(parts_dir, output_dir):
    """合并 .txt 分片并恢复原文件名与格式"""
    part_files = sorted(
        [os.path.join(parts_dir, f) for f in os.listdir(parts_dir) if f.lower().endswith(".txt")]
    )
    if not part_files:
        print("未找到分片文件")
        return
    # 先读取第一个文件的头信息，获取原文件名
    with open(part_files[0], 'rb') as pf:
        header_line = b""
        while True:
            ch = pf.read(1)
            if not ch or ch == b"\n":
                break
            header_line += ch
        original_filename = header_line.decode('utf-8')
        file_ext = os.path.splitext(original_filename)[1]  # 原始扩展名
        output_path = os.path.join(output_dir, original_filename)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_path, 'wb') as out_f:
        for idx, part in enumerate(part_files):
            with open(part, 'rb') as pf:
                if idx == 0:
                    # 第一个分片要跳过头信息
                    _ = pf.readline()  # 跳过文件名行
                    out_f.write(pf.read())
                else:
                    # 其他分片直接写入
                    _ = pf.readline()  # 跳过文件名行
                    out_f.write(pf.read())
            print(f"合并分片: {part}")
    print(f"合并完成: {output_path}")

