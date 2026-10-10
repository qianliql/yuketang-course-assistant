"""Play Rain Classroom videos normally and advance after native playback ends."""
import argparse
import json
import math
from pathlib import Path
import sys
import time
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Error as PlaywrightError
from auto_chrome import configured_course_url, scan_cdp_ports
from rain_course import find_catalog, extract_catalog

PLAYBACK_RATE = 2


def numbered_videos(info):
    videos = [task for task in info['tasks']
              if task['type'] == 0 and task['visible'] and task['path']]
    return [{**task, 'episode': index} for index, task in enumerate(videos, 1)]


def select_videos(videos, start_episode):
    if not 1 <= start_episode <= len(videos):
        raise ValueError(f'请输入 1 到 {len(videos)} 之间的集数。')
    if videos[start_episode - 1]['locked']:
        raise ValueError('这一集尚未开放，请选择其他集数。')
    return [task for task in videos if task['episode'] >= start_episode
            and not task['locked'] and (task['episode'] == start_episode or not task['completed'])]


def choose_start_episode(videos):
    if not videos:
        raise RuntimeError('课程目录中没有可播放的视频。')
    default = next((task['episode'] for task in videos
                    if not task['locked'] and not task['completed']),
                   next((task['episode'] for task in videos if not task['locked']), None))
    if default is None:
        raise RuntimeError('所有视频尚未开放。')
    print('\n视频列表（按课程目录顺序编号）：', flush=True)
    for task in videos:
        status = '未开放' if task['locked'] else '已完成' if task['completed'] else '未完成'
        print(f"  第 {task['episode']} 集：{task['name']} [{status}]", flush=True)
    while True:
        try:
            text = input(f'从第几集开始？输入 1–{len(videos)}，直接回车从第 {default} 集开始：').strip()
        except EOFError:
            print(f'未收到输入，默认从第 {default} 集开始。', flush=True)
            return default
        try:
            episode = int(text) if text else default
            select_videos(videos, episode)
            return episode
        except ValueError as exc:
            print(f'集数无效：{exc}', flush=True)


def find_video_frame(page, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError('播放窗口已关闭。')
        for frame in page.frames:
            try:
                if frame.evaluate('''() => {
                    const video=document.querySelector('video');
                    return Boolean(video && video.readyState>=2);
                }'''):
                    return frame
            except Exception:
                continue
        page.wait_for_timeout(500)
    raise RuntimeError('未找到播放器，可能需要验证或页面暂不支持。')


def navigation_error(error):
    return any(message in str(error) for message in (
        'Execution context was destroyed', 'Frame was detached',
        'Cannot find context with specified id', 'most likely because of a navigation'))


def player_state(frame):
    return frame.evaluate('''() => {
        const v=document.querySelector('video');
        if (!v) return null;
        const active=document.querySelector('.xt_video_player_speed .xt_video_player_common_active');
        return {time:v.currentTime,duration:v.duration,ended:v.ended,
            paused:v.paused,muted:v.muted,volume:v.volume,rate:v.playbackRate,
            menuRate:active?Number(active.getAttribute('data-speed')):null,
            error:v.error?{code:v.error.code,message:v.error.message}:null};
    }''')


def show_player_controls(frame):
    box=frame.locator('video').first.bounding_box()
    if box:
        frame.page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2,steps=5)


def set_native_speed(frame):
    """Use real pointer movement: this player's click handler rejects stationary clicks."""
    state=player_state(frame)
    if state and state['rate']==PLAYBACK_RATE and state['menuRate']==PLAYBACK_RATE:
        return
    show_player_controls(frame)
    speed=frame.locator('.xt_video_player_speed').first
    speed.hover(timeout=5000)
    option=speed.locator(f'li[data-speed="{PLAYBACK_RATE}"]')
    option.wait_for(state='visible',timeout=5000)
    box=option.bounding_box()
    if not box:
        raise RuntimeError('没有找到播放器的 2 倍速选项。')
    x=box['x']+box['width']/2
    y=box['y']+box['height']/2
    delta=min(4,box['width']/4)
    frame.page.mouse.move(x-delta,y,steps=6)
    frame.page.mouse.move(x+delta,y,steps=6)
    frame.page.mouse.down()
    frame.page.mouse.up()
    frame.wait_for_function('''rate => {
        const v=document.querySelector('video');
        const active=document.querySelector('.xt_video_player_speed .xt_video_player_common_active');
        return Boolean(v&&active&&v.playbackRate===rate&&Number(active.dataset.speed)===rate);
    }''',arg=PLAYBACK_RATE,timeout=3000)


def set_native_volume(frame,unmuted):
    state=player_state(frame)
    silent=state['muted'] or state['volume']==0
    if silent != (not unmuted):
        show_player_controls(frame)
        frame.locator('.xt_video_player_volume').first.click(timeout=5000)
        frame.wait_for_function('''unmuted => {
            const v=document.querySelector('video');
            return v && ((v.muted||v.volume===0)===!unmuted);
        }''',arg=unmuted,timeout=3000)


def learning_record_status(frame):
    return frame.evaluate('''() => {
        const player=document.querySelector('.xtplayer')?.__vue__?.$data?.player;
        const record=player?.heartBeat?.params;
        if (!record) return null;
        let pending=[];
        try {pending=Object.values(JSON.parse(localStorage.getItem('nhd')||'{}'));} catch(e) {}
        return {speed:record.sp,legacyCount:pending.filter(entry=>
            String(entry.v)===String(record.v)&&Number(entry.sp)===1).length};
    }''')


def start_video(page, unmuted=False, timeout=60):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        frame=find_video_frame(page,timeout=max(1,deadline-time.monotonic()))
        try:
            frame.evaluate('''() => {
                const video=document.querySelector('video');
                if (video.__courseSettingsHandler) {
                    for (const event of ['play','playing','loadedmetadata','ratechange','volumechange']) {
                        video.removeEventListener(event, video.__courseSettingsHandler);
                    }
                    delete video.__courseSettingsHandler;
                }
            }''')
            set_native_speed(frame)
            set_native_volume(frame,unmuted)
            if player_state(frame)['paused']:
                show_player_controls(frame)
                frame.locator('.xt_video_player_play_btn').first.click(timeout=5000)
            frame=find_video_frame(page,timeout=max(1,deadline-time.monotonic()))
            set_native_speed(frame)
            set_native_volume(frame,unmuted)
            state=player_state(frame)
            if state['paused'] and not state['ended']:
                continue
            return frame
        except PlaywrightError as exc:
            if not navigation_error(exc) or page.is_closed():
                raise
            page.wait_for_timeout(300)
    raise RuntimeError('播放器持续切换页面，暂时无法开始播放。')


def play_video(page, task, url, unmuted=False):
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.bring_to_front()
    frame = start_video(page,unmuted)
    record=learning_record_status(frame)
    if record:
        print(f"  播放器菜单已设为 2 倍速，当前学习记录倍速：{record['speed']}",flush=True)
        if record['legacyCount']>100:
            print('  旧学习记录仍待补传，完成度显示可能延后更新。',flush=True)
    last_position = None
    last_advance = time.monotonic()
    started = time.monotonic()
    duration_budget = 24 * 3600
    while True:
        if page.is_closed():
            raise RuntimeError('播放窗口已关闭。')
        try:
            state = player_state(frame)
        except PlaywrightError as exc:
            if not navigation_error(exc) or page.is_closed():
                raise
            print('  播放器页面正在切换，重新连接……',flush=True)
            frame=start_video(page,unmuted,timeout=45)
            last_position=None
            last_advance=time.monotonic()
            continue
        if not state:
            raise RuntimeError('播放器已消失，请检查页面。')
        if state['error']:
            raise RuntimeError(f"播放器错误：{state['error']}")
        duration = state.get('duration')
        if isinstance(duration, (int, float)) and math.isfinite(duration) and duration > 0:
            duration_budget = duration / PLAYBACK_RATE + 300
        if state['ended']:
            page.wait_for_timeout(2000)  # Let the site's own ended callback finish.
            return
        try:
            if state['rate']!=PLAYBACK_RATE or state['menuRate']!=PLAYBACK_RATE:
                set_native_speed(frame)
            if (state['muted'] or state['volume']==0) != (not unmuted):
                set_native_volume(frame,unmuted)
        except PlaywrightError as exc:
            if not navigation_error(exc) or page.is_closed():
                raise
            frame=start_video(page,unmuted,timeout=45)
            last_position=None
            last_advance=time.monotonic()
            continue
        if last_position is None or state['time'] > last_position + 0.01:
            last_position = state['time']
            last_advance = time.monotonic()
        if time.monotonic() - last_advance > 45:
            raise RuntimeError('视频暂停或卡住超过 45 秒，请检查登录、验证提示或课堂互动。')
        if time.monotonic() - started > duration_budget:
            raise RuntimeError('视频没有正常结束，请检查播放器。')
        page.wait_for_timeout(500)


def main():
    parser = argparse.ArgumentParser(description='雨课堂视频静音、2 倍速播放，结束后自动切换')
    parser.add_argument('--cdp-port', type=int, default=9223)
    parser.add_argument('--course-url', default=None)
    parser.add_argument('--play', action='store_true', help='实际开始播放；默认只列出目录')
    parser.add_argument('--limit', type=int, default=None, help='最多播放多少个视频')
    parser.add_argument('--unmuted', action='store_true', help='播放声音（默认静音）')
    parser.add_argument('--log-file', default=None, help='播放日志路径')
    parser.add_argument('--start-episode', type=int, default=None, help='从课程目录中的第几集开始')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit 必须大于 0')
    target_url = args.course_url or configured_course_url()
    if not scan_cdp_ports([args.cdp_port]):
        print('请双击 run-course.cmd 启动浏览器并登录课程。')
        return 1
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{args.cdp_port}')
        catalog = find_catalog(browser, target_url)
        info = extract_catalog(catalog)
        videos = numbered_videos(info)
        start_episode = args.start_episode
        if start_episode is None and args.play:
            start_episode = choose_start_episode(videos)
        tasks = select_videos(videos, start_episode) if start_episode is not None else [
            task for task in videos if not task['locked'] and not task['completed']]
        if args.limit is not None:
            tasks = tasks[:args.limit]
        print(f"课程：{info['course_name']}；待播放视频：{len(tasks)}")
        if not args.play:
            for task in tasks:
                print(f"  第 {task['episode']} 集：{task['name']}")
            print('只读检查完成。指定 --play 或双击 run-course.cmd 才会开始播放。')
            return 0
        if not tasks:
            print('没有可播放的未完成视频。')
            return 0
        page = catalog.context.new_page()
        journal = {'course_id':info['course_id'],'classroomid':info['classroomid'],
                   'start_episode':start_episode,'playback_rate':PLAYBACK_RATE,
                   'speed_method':'native_player_menu',
                   'muted':not args.unmuted,'played':[], 'error':None}
        output = Path(args.log_file) if args.log_file else Path(__file__).resolve().parent.parent / 'course-playback.json'
        try:
            for index, task in enumerate(tasks, 1):
                print(f"[{index}/{len(tasks)}] 第 {task['episode']} 集：{task['name']}（{'有声' if args.unmuted else '静音'}、2 倍速）", flush=True)
                play_video(page, task, urljoin(catalog.url, task['path']), args.unmuted)
                journal['played'].append({'id':task['id'],'name':task['name'],'episode':task['episode']})
                output.write_text(json.dumps(journal,ensure_ascii=False,indent=2),encoding='utf-8')
                print('  播放结束', flush=True)
            print('视频列表播放结束。平台记分请在课程目录中核对。')
            return 0
        except KeyboardInterrupt:
            journal['error'] = '用户停止播放'
            print('已停止。')
            return 130
        except Exception as exc:
            journal['error'] = str(exc)
            print(f'已停止：{exc}')
            return 1
        finally:
            output.write_text(json.dumps(journal,ensure_ascii=False,indent=2),encoding='utf-8')
            if not page.is_closed():
                page.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'无法运行：{exc}')
        sys.exit(1)
