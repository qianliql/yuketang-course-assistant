# 雨课堂课程助手

Windows 本地视频播放助手：读取已登录课程的目录，选择起始集数，通过播放器自带菜单设置静音和 2 倍速，并在视频自然结束后打开下一集。

## 功能

- 一个双击启动入口，自动打开专用 Edge / Chrome 浏览器并等待登录。
- 按完整视频目录编号选择起始集；回车默认选择第一个未完成且已开放的视频。
- 模拟鼠标移动并点击原生 `2.00X` 菜单，让播放速度与播放器内部设置同步。
- 每集自动静音；自然播放结束后自动换集。
- 起始集可重播，后续跳过已完成或未开放的视频。
- 防止重复启动，出错后保留运行窗口和提示。

## 安装

需要 Windows、Python 3.11 或更新版本，以及已安装的 Microsoft Edge 或 Google Chrome。

1. 下载项目 ZIP 并解压，或者克隆仓库。
2. 双击 `install.cmd` 安装依赖。安装过程需要联网，失败时按窗口提示处理。
3. 安装程序会将 `local-config.example.json` 复制为 `local-config.json`。编辑其中的 `course_url`，填入自己的雨课堂课程目录地址。格式为 `https://学校域名.yuketang.cn/pro/lms/课程标识/课堂编号/studycontent`。
4. 双击 `run-course.cmd`，在打开的浏览器中自行登录并进入课程目录。
5. 在运行窗口输入要开始的集数，或直接回车使用默认选择。

保持课程目录页和播放窗口打开。停止时在运行窗口按 `Ctrl+C`。

### 手动安装

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item local-config.example.json local-config.json
```

### 可选参数

```powershell
# 只检查启动和课程目录，不播放
.\run-course.cmd --check-only

# 直接从第 10 集开始
.\run-course.cmd --start-episode 10

# 最多播放 2 集
.\run-course.cmd --limit 2
```

## 数据保存

运行环境保存在 `.venv/`，专用浏览器登录资料保存在 `.browser-profile/`，播放日志为 `course-playback.json`。这些文件及个人课程配置均已排除在 Git 跟踪之外。不要提交浏览器资料、Cookie、账号凭据或课程日志。

浏览器调试服务只监听本机 `127.0.0.1:9223`。登录资料留在本机，程序不收集或上传到项目维护者。

## 适用范围与限制

支持采用相同课程目录和播放器结构的雨课堂学校版 `/pro/lms/` 页面。不同学校或平台升级可能需要调整选择器；未测试所有站点。

程序通过平台自带播放器正常播放视频，不提交讨论、作业或考试。播放结束与服务端记为完成是两件事，最终完成度以平台更新后的课程目录为准。暂停或卡住超过 45 秒时会停止并提示。请在自己有权限访问的课程中使用，并遵守课程及平台要求。

## 项目结构

```text
scripts/
  auto_chrome.py       浏览器启动与连接
  rain_course.py       课程目录读取
  rain_autoplay.py     播放器操作与换集
  run_local_course.py  整合启动流程
install.cmd           安装依赖
run-course.cmd        启动入口
local-config.example.json
requirements.txt
```

## 来源与许可证

本项目最初基于 [FlapPearLabs/xuetangx-complete](https://github.com/FlapPearLabs/xuetangx-complete) 部署，随后增加雨课堂原生播放适配，精简为目前的四个运行脚本。浏览器启动代码保留并修改了上游实现。

上游 README 声明使用 MIT 许可证。本项目按 MIT 许可证发布，保留上游来源与署名，见 [LICENSE](LICENSE) 和 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
