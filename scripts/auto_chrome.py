#!/usr/bin/env python3
"""
自动扫描CDP端口，接管Chrome
处理user-data-dir占用问题
"""
import urllib.request
import json
import os
import subprocess
import sys
import platform
import argparse
from pathlib import Path

def configured_course_url():
    config_path = Path(__file__).resolve().parent.parent / 'local-config.json'
    if config_path.is_file():
        return json.loads(config_path.read_text(encoding='utf-8-sig'))['course_url']
    raise ValueError('请先运行 install.cmd，并在 local-config.json 填入自己的雨课堂课程目录地址。')

def scan_cdp_ports(ports=range(9222, 9231)):
    """扫描本地CDP端口，返回第一个可用的"""
    for port in ports:
        try:
            req = urllib.request.Request(f'http://127.0.0.1:{port}/json/version')
            with urllib.request.urlopen(req, timeout=0.5) as response:
                info = json.load(response)
            if info.get('webSocketDebuggerUrl'):
                return port
        except:
            continue
    return None

def find_existing_chrome_port(user_data_dir):
    """检查指定user-data-dir是否已被Chrome占用，如果是，返回其端口"""
    lock_file = os.path.join(user_data_dir, 'SingletonLock')
    if os.path.exists(lock_file):
        # Chrome已锁定，尝试扫描端口
        return scan_cdp_ports()
    return None

def ensure_chrome(port=None, user_data_dir=None, auto_start=True, start_url=None):
    """确保Chrome已启动并返回CDP端口

    参数：
        port: 指定端口，None自动扫描
        user_data_dir: Chrome用户数据目录
        auto_start: True则尝试自动启动Chrome

    返回：(port, user_data_dir) 或 None（失败）
    """
    # 1. 扫描已有CDP端口
    requested_port = port
    if port is None:
        port = scan_cdp_ports()
    else:
        port = scan_cdp_ports([port])

    if port:
        # 端口存在，检查user-data-dir
        if user_data_dir:
            # 检查是否占用
            existing = find_existing_chrome_port(user_data_dir)
            if existing:
                print(f"⚠️ {user_data_dir} 已被占用，切换到新目录")
                user_data_dir = user_data_dir + '_brush'

        return port, user_data_dir

    # 2. 未找到CDP端口，尝试自动启动Chrome
    if not auto_start:
        return None, None

    # 检测Chrome路径
    chrome_path = None
    if platform.system() == 'Darwin':
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome Canary',
            os.path.expanduser('~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        ]
    elif platform.system() == 'Windows':
        candidates = [
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%LocalAppData%\Microsoft\Edge\Application\msedge.exe'),
        ]
    else:  # Linux
        candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
        ]

    for path in candidates:
        if os.path.exists(path):
            chrome_path = path
            break

    if not chrome_path:
        print("未找到 Chrome 或 Edge，请先安装其中一个浏览器。")
        return None, None

    # 设置user-data-dir
    if user_data_dir is None:
        user_data_dir = str(Path(__file__).resolve().parent.parent / '.browser-profile')

    # 检查是否被占用
    existing = find_existing_chrome_port(user_data_dir)
    if existing:
        print(f"⚠️ {user_data_dir} 已被占用，切换到新目录")
        user_data_dir = user_data_dir + '_brush'

    # 启动Chrome
    port = requested_port or 9223
    cmd = [
        chrome_path,
        f'--remote-debugging-port={port}',
        '--remote-debugging-address=127.0.0.1',
        f'--user-data-dir={user_data_dir}',
        '--no-first-run',
        '--no-default-browser-check',
        start_url or configured_course_url(),
    ]

    print(f"启动Chrome: port={port}, data_dir={user_data_dir}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 等待Chrome启动
    import time
    for i in range(30):
        time.sleep(1)
        if scan_cdp_ports([port]):
            return port, user_data_dir

    print("Chrome启动超时")
    return None, None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='启动项目专用 Chrome / Edge 浏览器')
    parser.add_argument('--port', type=int, default=9223)
    parser.add_argument('--url', default=None)
    args = parser.parse_args()
    port, _ = ensure_chrome(port=args.port, start_url=args.url)
    if not port:
        sys.exit(1)
    from playwright.sync_api import sync_playwright
    target_url = args.url or configured_course_url()
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        context = browser.contexts[0]
        if not any(page.url == target_url for page in context.pages):
            context.new_page().goto(target_url, wait_until='domcontentloaded', timeout=60000)
    print(f'浏览器连接就绪（端口 {port}）。请自行登录并打开课程学习页面。')
