//! Tauri 壳层入口：注册命令、管理 sidecar 生命周期。

pub mod crash;
pub mod sidecar;

use std::process::Child;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use sidecar::BackendInfo;
use tauri::{AppHandle, Emitter, Manager};

/// 应用级状态：后端连接信息 + 子进程句柄 + 重启串行化锁。
struct BackendState {
    info: Mutex<Option<BackendInfo>>,
    child: Mutex<Option<Child>>,
    restart_lock: Mutex<()>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            info: Mutex::new(None),
            child: Mutex::new(None),
            restart_lock: Mutex::new(()),
        }
    }
}

/// 供前端获取后端连接信息（port + token）。
#[tauri::command]
fn get_backend_info(state: tauri::State<'_, BackendState>) -> Option<BackendInfo> {
    state.info.lock().ok().and_then(|g| g.clone())
}

/// 重启后端进程（串行化，避免与健康巡检并发拉起多个 sidecar）。
#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> Result<Option<BackendInfo>, String> {
    restart_backend_impl(&app)
}

fn restart_backend_impl(app: &AppHandle) -> Result<Option<BackendInfo>, String> {
    let state = app.state::<BackendState>();
    let _guard = state.restart_lock.lock().unwrap();
    if let Ok(mut child) = state.child.lock() {
        if let Some(mut c) = child.take() {
            sidecar::shutdown(Some(&mut c));
        }
    }
    let working_dir = sidecar::default_working_dir();
    let (child, info) = sidecar::start_and_wait(&working_dir)?;
    *state.child.lock().unwrap() = Some(child);
    *state.info.lock().unwrap() = Some(info.clone());
    let _ = app.emit("backend-ready", ());
    Ok(Some(info))
}

/// 原生目录选择对话框（用于设置工作目录）。
#[tauri::command]
fn choose_directory(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    app.dialog()
        .file()
        .blocking_pick_folder()
        .and_then(|p| p.into_path().ok())
        .map(|pb| pb.to_string_lossy().into_owned())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    crash::install_panic_hook();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            let working_dir = sidecar::default_working_dir();

            // 后台线程拉起 sidecar，避免阻塞窗口启动；失败自动重试若干次
            std::thread::spawn(move || {
                let mut last_err = String::new();
                let attempts = 3;
                for attempt in 1..=attempts {
                    match sidecar::start_and_wait(&working_dir) {
                        Ok((child, info)) => {
                            let state = handle.state::<BackendState>();
                            *state.child.lock().unwrap() = Some(child);
                            *state.info.lock().unwrap() = Some(info.clone());
                            let _ = handle.emit("backend-ready", ());
                            return;
                        }
                        Err(e) => {
                            last_err = e;
                            if attempt < attempts {
                                std::thread::sleep(Duration::from_secs(2));
                            }
                        }
                    }
                }
                let _ = handle.emit("backend-error", last_err);
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_info,
            restart_backend,
            choose_directory
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    let shutting_down = Arc::new(AtomicBool::new(false));

    // 健康巡检：sidecar 意外退出则自动拉起，并更新连接信息（前端收到 backend-ready 后重连）
    {
        let handle = app.handle().clone();
        let sd_flag = Arc::clone(&shutting_down);
        std::thread::spawn(move || loop {
            std::thread::sleep(Duration::from_secs(3));
            if sd_flag.load(Ordering::Relaxed) {
                return;
            }
            let dead = {
                let state = handle.state::<BackendState>();
                let mut child = state.child.lock().unwrap();
                match child.as_mut() {
                    Some(c) => matches!(c.try_wait(), Ok(Some(_))),
                    None => false, // 尚未启动成功，交给 setup 线程处理
                }
            };
            if dead {
                let _ = restart_backend_impl(&handle);
            }
        });
    }

    // 应用退出时优雅杀掉 sidecar（整组 SIGKILL），避免孤儿进程累积
    app.run(move |app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            shutting_down.store(true, Ordering::Relaxed);
            let state = app_handle.state::<BackendState>();
            let _guard = state.restart_lock.lock().unwrap();
            let mut child = state.child.lock().unwrap();
            if let Some(ref mut c) = *child {
                sidecar::shutdown(Some(c));
            }
        }
    });
}
