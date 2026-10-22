from tkinter import Tk, messagebox
import re,sys,subprocess,os,random,requests,importlib,execjs
from assets.aira2c.aria2c_api import aria2_download
from core_lib import get_path
def _show_foreground_messagebox(show_dialog, title, message):
    root = Tk()
    root.withdraw()
    try:
        # 显式置顶父窗口，让 Windows 原生提示框继承置顶层级。
        root.attributes("-topmost", True)
        root.update_idletasks()
        return show_dialog(title, message, parent=root)
    finally:
        root.destroy()

def rand_ip():
    # 生成随机国内IP伪装来源, 否则蓝奏云下载域名会拦截到"网络异常"验证页
    first = random.choice(['61','66','113','116','117','118','119','120','121','122','123','124','125','171','175','182','183','202','210','211','218','219','220','221','222','223'])
    return first + '.' + '.'.join(str(random.randint(0,255)) for _ in range(3))
def get_direct_link(url):
    # 第0层 获取页面：老页面有 arg1 挑战，新页面直接给 iframe fn
    response = requests.get(url)
    response_clear = re.sub(r'\s', '', response.text)
    fn = re.findall('/fn?(.*?)" frameborder="0" scrolling="no"></iframe>', response.text)

    arg1 = re.findall("arg1='(.*?)'", response_clear)
    if not fn and arg1:
        # 老式防护挑战页：先解 acw_sc__v2 cookie 再取 fn
        with open(get_path('scripts/func_arg3.js'), 'r', encoding='utf-8') as f:
            js_code = f.read()
        ctx = execjs.compile(js_code)
        arg3 = ctx.call('main', arg1[0])
        cookies = {"acw_sc__v2": arg3}
        response = requests.get(url, cookies=cookies)
        fn = re.findall('/fn?(.*?)" frameborder="0" scrolling="no"></iframe>', response.text)
        if not fn and 'arg1' in response.text:
            # 防护挑战可能连续出现，重新计算再取一次
            arg1b = re.findall("arg1='(.*?)'", re.sub(r'\s', '', response.text))
            if arg1b:
                arg3 = ctx.call('main', arg1b[0])
                response = requests.get(url, cookies={"acw_sc__v2": arg3})
                fn = re.findall('/fn?(.*?)" frameborder="0" scrolling="no"></iframe>', response.text)
    # print('fn:', fn)
    if not fn:
        print("蓝奏页面解析失败：未找到 fn 直链参数")
        return None
    # 第二层 取出第三步的sign
    url2 = "https://jitianna.lanzoul.com/fn?"+str(fn[0])
    dict1 = {'referer': url}
    response2 = requests.get(url2, data=dict1)
    wp_sign = re.findall("wp_sign = '(.*?)'", response2.text)
    # 2026-09 接口改版: 解析接口由 ajaxm.php 换为 ajaxfile.php,
    # websignkey/signs 不再固定为 pg5H, 由 fn 页变量 ajaxdata 提供
    ajaxdata = re.findall("var ajaxdata = '(.*?)'", response2.text)
    if ajaxdata:
        ajax_api = 'ajaxfile.php'
        websignkey = ajaxdata[0]
    else:
        ajax_api = 'ajaxm.php'  # 旧版页面兼容
        websignkey = 'pg5H'
    # 第三层 取跳转链
    var = re.findall('var fid = (\\d+);', response.text)
    # ajax 接口域名优先从 fn 页面提取，蓝奏已迁移到 apifile.woozooo.com；
    # 老域名会返回 407 风控导致下载失败
    ajax_page = re.findall(r"url\s*:\s*'(https?://[^']*?ajaxfile\.php\?file=\d+)'", response2.text)
    if ajax_page:
        url3 = ajax_page[0]
    else:
        url3 = 'https://apifile.woozooo.com/' + ajax_api + '?file=' + str(var[0])

    data={"action":"downprocess", "websignkey":websignkey, "signs":websignkey,"sign":wp_sign,"websign":"","kd":"1","ves":"1" }
    headers={'referer':url2,'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'}

    url4 = requests.post(url3,data=data,headers=headers)
    try:
        msg = url4.json()
    except ValueError:
        print("ajax接口返回异常:", url4.text[:200])
        return None
    if str(msg.get('zt')) != '1':
        print("解析失败:", msg.get('inf'))
        return None
    # 新版返回 dom+url(url自带?前缀), 旧版url不带?, 统一拼成 dom/file/?xxx
    dom = str(msg.get('dom') or 'https://developer-oss.lanrar.com').replace('\\/','/')
    download_link = str(msg.get('url')).replace('\\/','/')
    if not download_link.startswith('?'):
        download_link = '?' + download_link
    good_link = dom + '/file/' + download_link

    # 2026-09: 旧的 developer-oss 固定域名+大段浏览器头已失效,
    # 跳转链需带随机IP伪装头才返回302真实直链, 否则被拦截到"网络异常"验证页
    headers2 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
        "Accept": "*/*",
        "Accept-Language": "zh-cn",
        "Cookie": "down_ip=1",
        "referer": "https://jitianna.lanzoul.com/",
        "X-FORWARDED-FOR": rand_ip(),
        "CLIENT-IP": rand_ip(),
    }
    #第四层 获取真实直链地址
    resp = requests.get(good_link, allow_redirects=False, headers=headers2)     # 禁止自动重定向

    # 2026-09: 跳转链可能被 CDN 拦截返回 arg1 挑战页，需解 acw_sc__v2 cookie 后重试；
    # 挑战可能连续出现多次，循环解算直到拿到 location
    for _ in range(5):
        if 'location' in resp.headers:
            break
        if "arg1=" not in resp.text:
            break
        arg1_c = re.findall("arg1='(.*?)'", re.sub(r'\s', '', resp.text))
        if not arg1_c:
            break
        with open(get_path('scripts/func_arg3.js'), 'r', encoding='utf-8') as f:
            js_code = f.read()
        ctx = execjs.compile(js_code)
        arg3_c = ctx.call('main', arg1_c[0])
        headers2["Cookie"] = headers2.get("Cookie", "") + "; acw_sc__v2=" + arg3_c
        resp = requests.get(good_link, allow_redirects=False, headers=headers2)

    # 打印 location 值
    if 'location' in resp.headers:
        #print("跳转地址：", resp.headers['location'])
        return resp.headers['location']
    else:
        print("没有发现 location 头")
        return None

def download_file(url, save_path, auto_title=True):
    """
    下载文件，可根据 auto_title 决定保存路径
    :param url: 蓝奏网页地址
    :param save_path: 保存目录或完整路径
    :param auto_title: True → 用内部获取的 title 作为文件名（save_path 是目录）
                      False → save_path 必须包含文件名
    :return: True/False
    """
    # 第一层 获取页面标题与直链（内部兼容老式 arg1 挑战页与新式 iframe 页）
    response = requests.get(url)
    title = re.findall('<title>(.*?) - 蓝奏云</title>', response.text)
    if not title:
        print("蓝奏页面标题解析失败")
        return False
    title = title[0]
    url_link = get_direct_link(url=url)
    # print('url_link:', url_link)
    if auto_title:
        # 确保目录存在
        os.makedirs(save_path, exist_ok=True)
        save_path = os.path.join(save_path, title)
    try:
        # 直接使用 requests 下载可能会被服务器限制，改用 aria2c 多线程下载
        # with requests.get(url_link, stream=True) as r:
        #     r.raise_for_status()
        #     with open(save_path, 'wb') as f:
        #         for chunk in r.iter_content(chunk_size=8192):
        #             if chunk:
        #                 f.write(chunk)
        aria2_download(url_link, threads=16, path=os.path.dirname(save_path))
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False
def get_server_version(url):
    try:
        resp = requests.get(url,timeout=2)
        resp.raise_for_status()
        version = re.findall(r'ief":"A@最新版本号:(.*?)@A', resp.text)[0]
        version_root = re.findall(r'B@最新内核号:(\d+)@BC', resp.text)[0]
        version_info = re.findall(r'@BC@说明:(.*?)@CD@', resp.text)[0]
        download_server_url = re.findall('D@url:(.*?)@D', resp.text)[0]
        url_split = re.findall('@(.*?)@', download_server_url)
        if len(url_split) <= 2:
            links = ['https://jitianna.lanzoul.com/' + x for x in url_split]
        elif 'C\\u003C/div>\\u003Cdiv>D' not in url_split:
            links = ['https://jitianna.lanzoul.com/' + x for x in url_split]
        else:
            times = url_split.index('C\\u003C/div>\\u003Cdiv>D')
            links = ['https://jitianna.lanzoul.com/' + x for x in url_split[times + 1:]]
        return [version, int(version_root), str(version_info), links]
    except (requests.RequestException, IndexError, ValueError):
        return None

def get_main_program_path():
    """
    获取当前运行的主程序路径和所在目录
    返回 [程序路径, 程序目录]
    """
    # 如果是打包成 exe 运行
    if getattr(sys, 'frozen', False):
        program_path = os.path.abspath(sys.executable)
    # 如果是普通 python 脚本运行
    else:
        program_path = os.path.abspath(sys.argv[0])

    program_dir = os.path.dirname(program_path)
    return [program_path, program_dir]

def create_update_helper(urls):
    program_path = get_main_program_path()[0].replace("\\", "\\\\")
    program_dir = get_main_program_path()[1]
    helper_path = os.path.join(program_dir, "update_helper.py")
    bat_path2 = helper_path + ".bat"
    bat_path = bat_path2.replace("\\", "\\\\")
    program_dir = program_dir.replace("\\", "\\\\")
    helper_path = helper_path.replace("\\", "\\\\")

    # 写入 update_helper.py
    with open(helper_path, "w", encoding="utf-8") as f:
        f.write(f"""

import os, time, subprocess, sys, random, requests,re
def rand_ip():
    first = random.choice(['61','66','113','116','117','118','119','120','121','122','123','124','125','171','175','182','183','202','210','211','218','219','220','221','222','223'])
    return first + '.' + '.'.join(str(random.randint(0,255)) for _ in range(3))
def get_direct_link(url):
    response1 = requests.get(url)
    fn =  re.findall('/fn?(.*?)" frameborder="0" scrolling="no"></iframe>', response1.text)
    url2 = "https://jitianna.lanzoul.com/fn?"+str(fn[0])
    dict1={{'referer': url}}
    response2 = requests.get(url2,data=dict1)
    wp_sign=re.findall("wp_sign = '(.*?)'",response2.text)
    ajaxdata=re.findall("var ajaxdata = '(.*?)'",response2.text)
    if ajaxdata:
        ajax_api='ajaxfile.php'
        websignkey=ajaxdata[0]
    else:
        ajax_api='ajaxm.php'
        websignkey='pg5H'
    var =  re.findall('var fid = (\\\\d+);', response1.text)
    url3 = 'https://jitianna.lanzoul.com/'+ajax_api+'?file='+str(var[0])
    data={{"action":"downprocess", "websignkey":websignkey, "signs":websignkey,"sign":wp_sign,"websign":"","kd":"1","ves":"1" }}
    headers={{'referer':url2,'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0'}}
    url4 = requests.post(url3,data=data,headers=headers)
    try:
        msg = url4.json()
    except ValueError:
        print("ajax接口返回异常")
        return None
    if str(msg.get('zt')) != '1':
        print("解析失败:", msg.get('inf'))
        return None
    dom = str(msg.get('dom') or 'https://developer-oss.lanrar.com').replace('\\/','/')
    download_link = str(msg.get('url')).replace('\\/','/')
    if not download_link.startswith('?'):
        download_link = '?' + download_link
    good_link = dom + '/file/' + download_link
    headers2 = {{
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
        "Cookie": "down_ip=1",
        "referer": "https://jitianna.lanzoul.com/",
        "X-FORWARDED-FOR": rand_ip(),
        "CLIENT-IP": rand_ip(),
    }}
    resp = requests.get(good_link, allow_redirects=False,headers=headers2)
    if 'location' in resp.headers:
        return resp.headers['location']
    else:
        print("location")


time.sleep(0.1)
current_file = "{program_path}" 
current_dir = "{program_dir}"
urls_list = {urls}
Self_cache = os.path.join(os.path.expanduser('~'), "PyCache",'Self_cache')


def download_file(urls_list, save_path, auto_title=True):
    response = requests.get(urls_list)
    title = re.findall('<title>(.*?) - 蓝奏云</title>', response.text)[0] 
    if title.endswith(".py.txt"):
        title = title[:-4]
    url_link = get_direct_link(url=urls_list)
    if auto_title:
        save_path = os.path.join(save_path, title)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with requests.get(url_link, stream=True) as r:
        r.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return title

def merge_file(parts_dir, output_dir):
    part_files = sorted(
        [os.path.join(parts_dir, f) for f in os.listdir(parts_dir) if f.lower().endswith(".txt")]
    )
    if not part_files:
        return
    with open(part_files[0], 'rb') as pf:
        header_line = b""
        while True:
            ch = pf.read(1)
            if not ch or ch == b"\\n":
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
    return original_filename  # 返回文件名

def self_delete():
    with open('{bat_path}', "w") as f:
        f.write(f'''
@echo off
:loop
del {helper_path} >nul 2>&1
if exist {helper_path} goto loop
del {bat_path} >nul 2>&1
exit'''
)



    subprocess.Popen(['{bat_path}'], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit() # 退出更新器


if len(urls_list)==1:
    final_title = download_file(urls_list[0], current_dir, auto_title=True)
else:
    # 清理上次的缓存
    if os.path.isdir(Self_cache):  # 目录存在才进入
        for filename in os.listdir(Self_cache):
            file_path = os.path.join(Self_cache, filename)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

    for url in urls_list:
        download_file(url, Self_cache, auto_title=True) #多片
    final_title = merge_file(Self_cache, current_dir)

#如果是一个文件，直接用蓝奏云内的标题
#如果是多文件，用合成文件获得的文件名

open_path = os.path.join(current_dir,final_title)

if open_path.lower().endswith('.exe'):
    subprocess.Popen([open_path], creationflags=subprocess.CREATE_NO_WINDOW)
else:
    subprocess.Popen(["python",os.path.join(current_dir,final_title)], creationflags=subprocess.CREATE_NO_WINDOW)

time.sleep(0.1)
self_delete()

        """)
    subprocess.Popen(["python", helper_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit()  # 退出更新主程序

# 检测本地是否有蓝奏模块,如果没有,下载,以便于helper内强制调用
def check_loacl_lanzoui():
    # 本地指令
    if os.path.isfile('D:/GAMEMODE 1'):
        return 1

# 云控
def total_control():
    if check_loacl_lanzoui():
        return 1
    try:
        responses = requests.get(
            'https://sharechain.qq.com/302a3da0abb6155d3357dd71b94bf8c1',
            timeout=5,
        ).text
        import MainGUI
        a = re.findall('✘(.*?)✘', responses)
        if not a:
            return 0
        b = a[-1]
        v = MainGUI.VERSION_CODE()
        for i in a:
            try:  # 将最后一个字符串转化小数点报错跳过
                if float(i)*100 == float(v):
                    _show_foreground_messagebox(messagebox.showinfo, "版本验证", b)
                    sys.exit(0)
            except:  # 占位
                pass
    except Exception:
        # 云控接口异常时静默跳过，不影响程序启动
        return 0
    return 0
def version_detection(weiyun_update_url, now_version, now_version_root):
    if check_loacl_lanzoui():
        return 1
    server_version = get_server_version(weiyun_update_url)
    if not server_version:
        # 更新服务器不可用或返回格式已变更时，只跳过检测，不阻断程序启动
        print("版本检测：更新服务器暂不可用，已跳过本次更新检测。")
        return 0
    if int(server_version[1]) <= int(now_version_root):
        _show_foreground_messagebox(
            messagebox.showinfo, "版本检测", f"当前已是最新版本（{now_version}）"
        )
    else:
        if _show_foreground_messagebox(
                messagebox.askyesno,
                "发现新版本",
                f"本地版本：{now_version}\n最新版本：{server_version[0]}\n更新介绍：{server_version[2]}\n是否更新？"
        ):
            #执行更新函数
            server_version = get_server_version(weiyun_update_url)[3]
            create_update_helper(server_version)

if __name__ == "__main__":
    pass
    # download_file('https://jitianna.lanzoul.com/iTgUC35dcvte', 'D:\\Download_test')
    #print(get_direct_link('https://jitianna.lanzoul.com/iTgUC35dcvte'))
