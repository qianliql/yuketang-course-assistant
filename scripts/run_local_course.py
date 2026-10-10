"""One entry point: start browser, wait for login, inspect course, then play."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from auto_chrome import configured_course_url, ensure_chrome
from rain_course import parse_rain_url, find_catalog, extract_catalog
from rain_autoplay import numbered_videos, select_videos, choose_start_episode

ROOT = Path(__file__).resolve().parent.parent


def open_course_tab(browser, url):
    for context in browser.contexts:
        for page in context.pages:
            if page.url.rstrip('/') == url.rstrip('/'):
                return page
    page = browser.contexts[0].new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    return page


def wait_for_course(browser, target_url, timeout):
    deadline = time.monotonic() + timeout
    latest_error = '课程页面尚未加载'
    print('请在浏览器中登录并打开课程目录，识别成功后可选择开始集数。', flush=True)
    while time.monotonic() < deadline:
        pages = [page for context in browser.contexts for page in context.pages
                 if urlparse(page.url).hostname == urlparse(target_url).hostname]
        if not pages:
            raise RuntimeError('课程浏览器页面已关闭，请重新双击 run-course.cmd。')
        try:
            page = find_catalog(browser, target_url)
            return extract_catalog(page)
        except Exception as exc:
            latest_error = str(exc)
        pages[-1].wait_for_timeout(1000)
    raise RuntimeError(f'等待登录或课程加载超时：{latest_error}。重新双击即可重试。')


def main():
    parser = argparse.ArgumentParser(description='课程助手：打开浏览器、识别课程、自动播放')
    parser.add_argument('--cdp-port', type=int, default=9223)
    parser.add_argument('--course-url', default=None)
    parser.add_argument('--check-only', action='store_true', help='检查到课程后结束，不开始播放')
    parser.add_argument('--wait-timeout', type=int, default=600)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--log-file', default=None)
    parser.add_argument('--start-episode', type=int, default=None)
    args = parser.parse_args()
    target_url = args.course_url or configured_course_url()
    if urlparse(target_url).scheme != 'https' or not parse_rain_url(target_url):
        raise ValueError('请在 local-config.json 配置有效的雨课堂 HTTPS 课程目录地址。')
    print('课程助手正在启动……', flush=True)
    port, _ = ensure_chrome(port=args.cdp_port, start_url=target_url)
    if not port:
        raise RuntimeError('无法启动课程浏览器。')
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        course_page = open_course_tab(browser, target_url)
        if not args.check_only and course_page.url.rstrip('/') == target_url.rstrip('/'):
            course_page.reload(wait_until='domcontentloaded', timeout=60000)
        info = wait_for_course(browser, target_url, args.wait_timeout)
        tasks = [task for task in info['tasks'] if task['type']==0
                 and task['visible'] and not task['locked'] and not task['completed']]
        print(f"已识别：{info['course_name']}，待播放视频 {len(tasks)} 个。", flush=True)
    if args.check_only:
        print('启动和课程识别检查通过。', flush=True)
        return 0
    scripts = ROOT / 'scripts'
    videos = numbered_videos(info)
    start_episode = args.start_episode if args.start_episode is not None else choose_start_episode(videos)
    select_videos(videos,start_episode)
    print(f'从第 {start_episode} 集开始，每个视频自动静音、2 倍速。',flush=True)
    command = [sys.executable,'-u',str(scripts/'rain_autoplay.py'),
               '--cdp-port',str(port),'--course-url',target_url,'--play',
               '--start-episode',str(start_episode)]
    if args.limit is not None:
        command += ['--limit',str(args.limit)]
    if args.log_file:
        command += ['--log-file',args.log_file]
    print('开始运行。需要停止时按 Ctrl+C。', flush=True)
    child = subprocess.Popen(command)
    try:
        return child.wait()
    except KeyboardInterrupt:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        print('已停止。')
        return 130


if __name__ == '__main__':
    # A Windows file lock prevents two double-clicks from creating duplicate runs.
    lock = (ROOT / '.course-run.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b'0');lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                print('课程助手已经在运行，请使用已打开的运行窗口。')
                sys.exit(1)
        sys.exit(main())
    except KeyboardInterrupt:
        print('已停止。')
        sys.exit(130)
    except Exception as exc:
        print(f'无法运行：{exc}')
        sys.exit(1)
    finally:
        lock.close()
