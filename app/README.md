# Xiaomi Remote Agent：开发与离线构建

用户安装、按键与人工验收见 [仓库根 README](../README.md)。本目录只构建小米蓝牙语音遥控器 2 / 2 Pro 的独立 Windows 程序，运行不依赖 MiVibe Remote。

基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改，上游提交 `34d5244`，保留原作者与贡献者版权，采用 [GPL-3.0](LICENSE)。架构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 本地前提

- 64 位 Windows，依赖已安装到本目录 `.venv`；当前本地解释器是 Python 3.11.9。
- 所有 Python 命令使用 `.venv\Scripts\python.exe`；依赖版本见 `requirements.txt` 和 `requirements-dev.txt`。构建不安装包、不下载依赖。
- 系统 .NET Framework 64 位编译器 `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` 及 WPF 引用程序集。
- 人工准备的 Frida Gadget 17.15.3 位于 `source/bridges/xiaomi/assets/frida-gadget-17.15.3-windows-x86_64.dll.xz`，构建校验 SHA-256；许可文本位于 `licenses/frida-COPYING.txt`。
- Inno Setup / ISCC 可选，找不到时保留文件夹产物并跳过安装包。

## 检查与构建

在 `app/` 目录依次运行：

```powershell
.\.venv\Scripts\python.exe -m compileall -q source
.\.venv\Scripts\python.exe -m ruff check source/standalone/xiaomi_main.py source/bridges/xiaomi --select F
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\delivery\build-standalone-packages.ps1
```

产物位于**仓库根目录** `dist\XiaomiRemoteAgent\`。主程序、`remote-helper.exe`、`_internal`、Frida Gadget、GPL 和第三方许可证一起交付。不要启动产物来代替静态检查；真实遥控器连接和系统录音设备变更由人验收。

构建脚本用 Pillow 生成 `source/assets/app.ico`，使用 `source/XiaomiRemoteAgent.spec` 打包无控制台主程序，再用系统 csc 的 `/target:winexe` 编译 `helper/remote-helper.cs`。PyInstaller 缓存放在工作区 `app/build/`。没有签名的本地产物可供人工验收；本项目不包含在线自动更新。

单元测试使用临时目录与 mock 验证配置、动态 AppID、helper 参数与动作调度、隐藏子进程、录音设备备份/恢复及错误处理。这些结果不代表蓝牙、音质、桌面 UI 自动化已经通过实机验收。

## 维护边界

- 保留 ATVV、音频路由、Raw Input 与 HID 报告兼容层，不重写已验证的协议路径。
- 所有受管 Python 子进程使用 `CREATE_NO_WINDOW` 和隐藏 `STARTUPINFO`；提权注入器使用 `SW_HIDE`。helper 动作直接传参数数组给随程序发布的 exe，不使用 PowerShell。
- 配置与主日志位于 `%APPDATA%\XiaomiRemoteAgent`，Gadget 受保护运行目录位于 `%PROGRAMDATA%\XiaomiRemoteAgent\hid-tap`。
- 不操作已安装 MiVibe 的目录和配置，冲突检查只读取进程名。
- `helper/audio-default-reference.ps1` 仅作为原始实现参考；默认录音设备功能使用 Python ctypes，不执行该脚本。
- 本轮仅做离线检查和构建；按键、10 次连续语音、长按、重连、黑框和录音角色恢复须按根 README 人工验收。

上游项目：<https://github.com/wyuzhi/MiVibe-Remote>；本项目：<https://github.com/sumian-buff/xiaomi-remote-agent>。第三方许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
