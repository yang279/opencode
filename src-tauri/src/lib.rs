//! Tauri 壳层入口：注册命令、管理 sidecar 生命周期。

pub mod sidecar;

use std::process::Child;
use std::sync::Mutex;

use sidecar::BackendInfo;
use tauri::{Emitter, Manager};

/// 应用级状态：后端连接信息 + 子进程句柄。
struct BackendState {
    info: Mutex<Option<BackendInfo>>,
    child: Mutex<Option<Child>>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            info: Mutex::new(None),
            child: Mutex::new(None),
        }
    }
}

/// 供前端获取后端连接信息（port + token）。
#[tauri::command]
fn get_backend_info(state: tauri::State<'_, BackendState>) -> Option<BackendInfo> {
    state.info.lock().ok().and_then(|g| g.clone())
}

/// 重启后端进程。
#[tauri::command]
fn restart_backend(
    app: tauri::AppHandle,
    state: tauri::State<'_, BackendState>,
) -> Result<Option<BackendInfo>, String> {
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
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            let working_dir = sidecar::default_working_dir();

            // 后台线程拉起 sidecar，避免阻塞窗口启动
            std::thread::spawn(move || match sidecar::start_and_wait(&working_dir) {
                Ok((child, info)) => {
                    let state = handle.state::<BackendState>();
                    *state.child.lock().unwrap() = Some(child);
                    *state.info.lock().unwrap() = Some(info.clone());
                    let _ = handle.emit("backend-ready", ());
                }
                Err(e) => {
                    let _ = handle.emit("backend-error", e);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_info,
            restart_backend,
            choose_directory
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}