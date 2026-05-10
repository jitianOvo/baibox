import os
import subprocess
def aria2_download(url, threads=16, headers=None, cookie=None, filename=None, path=".", min_split_size="1M"):
    """
    aria2 极速多线程下载（plus版）
    参数:
    url           下载链接
    threads       线程数，建议16，并非越大越快（受限于磁盘/服务器）
    headers       dict 形式 header
    cookie        dict 或 str
    filename      保存文件名 (None = 服务器名)
    path          保存目录
    min_split_size 分段最小单位（如 '1M'），建议不低于1M
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(base_dir, "aria2c.exe")  # 选中当前目录下的 aria2c.exe

    cmd = [
        exe_path,
        url,
        "-x", str(threads),  # 单服务器最大连接数
        "-s", str(threads),  # 分段数
        "-k", min_split_size,  # 每段大小
        "-d", path,  # 保存目录
        "--continue=true",  # 断点续传
        "--summary-interval=1",
        "--max-connection-per-server=" + str(threads),
        "--split=" + str(threads),
        "--min-split-size=" + min_split_size,  # 确保分段不会过小（建议1M以上）
        "--retry-wait=2",  # 重试等待时间
        "--max-tries=15",  # 最大重试次数
        "--timeout=60",  # 超时时间
        "--check-certificate=false",  # 某些直链可禁用证书检测
    ]
    if filename:
        cmd += ["-o", filename]

    headers = headers.copy() if headers else {}
    if cookie:
        if isinstance(cookie, dict):
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookie.items())
        else:
            cookie_str = cookie
        headers["Cookie"] = cookie_str

    for k, v in headers.items():
        cmd += ["--header", f"{k}: {v}"]

    # print("执行命令:")
    # print(" ".join(cmd))

    subprocess.run(cmd)