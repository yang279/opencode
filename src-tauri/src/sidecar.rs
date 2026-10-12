//! sidecar 生命周期管理：拉起 Python 后端、读取握手信息、优雅退出。

use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::Duration;

#[cfg(unix)]
use std::os::unix::process::CommandExt;

/// 后端连接信息，经 stdout 握手行解析得到。
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BackendInfo {
    pub port: u16,
    pub token: String,
}

/// 拉起后端进程并阻塞等待握手行。
///
/// 启动策略：
/// 1. env `MYOPENCODE_SIDECAR` 存在 → 直接按该命令启动（开发模式，
///    通常是 `python3 -m myopencode`）。
/// 2. 否则尝试同目录的 `myopencode-sidecar` 二进制（发布模式，由
///    `scripts/build-sidecar.sh` + Tauri `externalBin` 打包）。
pub fn start_and_wait(working_dir: &str) -> Result<(Child, BackendInfo), String> {
    let mut cmd = build_command(working_dir);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::inherit());
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("无法启动后端进程: {e}"))?;

    let info = read_handshake(&mut child)?;
    // 握手打印在 uvicorn 实际监听端口之前，这里先探测端口真正就绪，
    // 避免前端拿到 {port, token} 后立刻连接却失败。
    wait_port_ready(info.port, Duration::from_secs(15))?;
    Ok((child, info))
}

/// 轮询探测 `127.0.0.1:port` 是否已可连接，直到超时。
fn wait_port_ready(port: u16, timeout: Duration) -> Result<(), String> {
    let deadline = std::time::Instant::now() + timeout;
    loop {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        if std::time::Instant::now() > deadline {
            return Err(format!(
                "后端端口 {} 未在 {:.1}s 内就绪",
                port,
                timeout.as_secs_f64()
            ));
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

/// 默认工作目录：优先 $HOME/myopencode（固定专用工作区，不存在则创建），
/// 其次 $HOME，最后回退 cwd。
///
/// 桌面 App 从 Finder 双击启动时 `current_dir()` 是 `/`，绝不能拿它当 workspace，
/// 否则沙箱会把根目录当作工作区（读越界/写根目录等一系列问题）。
pub fn default_working_dir() -> String {
    if let Ok(home) = std::env::var("HOME") {
        let workspace = std::path::Path::new(&home).join("myopencode");
        if std::fs::create_dir_all(&workspace).is_ok() {
            return workspace.to_string_lossy().into_owned();
        }
        return home;
    }
    std::env::current_dir()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_else(|_| ".".to_string())
}

/// 构造后端启动命令。
fn build_command(working_dir: &str) -> Command {
    if let Ok(sidecar) = std::env::var("MYOPENCODE_SIDECAR") {
        let parts: Vec<String> = sidecar
            .split_whitespace()
            .map(|s| s.to_string())
            .collect();
        let (program, args) = parts.split_first().expect("sidecar 命令为空");
        let mut cmd = Command::new(program);
        cmd.args(args);
        cmd.arg("--working-dir").arg(working_dir);
        apply_python_env(&mut cmd);
        cmd.current_dir(working_dir);
        #[cfg(unix)]
        {
            cmd.process_group(0);
        }
        return cmd;
    }

    // 发布模式：与主二进制同目录下的 sidecar（externalBin 打包）
    // macOS: <app>.app/Contents/MacOS/；Windows/Linux: 与可执行文件同目录
    let path = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
        .map(|p| p.join("myopencode-sidecar"))
        .unwrap_or_else(|| PathBuf::from("./myopencode-sidecar"));
    let mut cmd = Command::new(path);
    cmd.arg("--working-dir").arg(working_dir);
    cmd.current_dir(working_dir);
    #[cfg(unix)]
    {
        cmd.process_group(0);
    }
    cmd
}

/// 用 python 启动时补充 PYTHONPATH，让 `-m myopencode` 可定位到源码。
fn apply_python_env(cmd: &mut Command) {
    if let Ok(env_pythonpath) = std::env::var("MYOPENCODE_PYTHONPATH") {
        cmd.env("PYTHONPATH", env_pythonpath);
    }
}

/// 从子进程 stdout 读取握手行，返回解析后的 BackendInfo。
fn read_handshake(child: &mut Child) -> Result<BackendInfo, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "后端进程无 stdout".to_string())?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();

    let deadline = std::time::Instant::now() + Duration::from_secs(30);
    loop {
        if !line.is_empty() {
            break;
        }
        if std::time::Instant::now() > deadline {
            let _ = child.kill();
            return Err("等待后端握手超时".to_string());
        }
        match reader.read_line(&mut line) {
            Ok(0) => {
                let _ = child.wait();
                return Err("后端进程提前退出".to_string());
            }
            Ok(_) => line = line.trim().to_string(),
            Err(e) => return Err(format!("读取握手失败: {e}")),
        }
    }

    serde_json::from_str::<BackendInfo>(&line)
        .map_err(|e| format!("握手行解析失败: {e}"))
}

/// 终止整个 sidecar 进程组（PyInstaller onefile 是「引导器 + Python 子进程」，
/// 单杀引导器会留下孤儿 Python 进程），然后回收。
pub fn shutdown(child: Option<&mut Child>) {
    if let Some(c) = child {
        #[cfg(unix)]
        {
            // process_group(0) 让子进程成为组长，PGID == 其 PID，kill 负 PID 杀整组
            let pid = c.id() as i32;
            unsafe {
                libc::kill(-pid, libc::SIGKILL);
            }
        }
        #[cfg(not(unix))]
        {
            let _ = c.kill();
        }
        let _ = c.wait();
    }
}