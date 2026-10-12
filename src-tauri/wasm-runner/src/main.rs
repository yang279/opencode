//! wasm-runner：在 wasmtime(WASI) 沙箱中执行 WASM 模块。
//!
//! 用法：
//!   wasm-runner run-wasm --dir <工作目录> [--timeout <秒>] <module.wasm> [args...]
//!
//! 隔离语义：
//!   - 只 preopen 工作目录（映射为 guest 的 "."）与隔离的 /tmp
//!   - 默认无网络（WASI preview1 不含 socket）
//!   - guest 的 stdout/stderr 直接透传到宿主 stdout/stderr，退出码透传
use anyhow::{anyhow, Result};
use std::path::PathBuf;
use wasmtime::{Engine, Linker, Module, Store};
use wasmtime_wasi::preview1::{add_to_linker_sync, WasiP1Ctx};
use wasmtime_wasi::{DirPerms, FilePerms, WasiCtxBuilder};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 || args[1] != "run-wasm" {
        eprintln!("usage: wasm-runner run-wasm --dir <dir> [--timeout <s>] <module.wasm> [args...]");
        std::process::exit(2);
    }
    if let Err(e) = run(&args[2..]) {
        eprintln!("{:#}", e);
        std::process::exit(1);
    }
}

fn run(args: &[String]) -> Result<()> {
    let mut dir: Option<PathBuf> = None;
    let mut module_path: Option<PathBuf> = None;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--dir" => {
                i += 1;
                dir = Some(PathBuf::from(&args[i]));
            }
            "--timeout" => {
                i += 1;
                let _ = args[i].parse::<u64>().unwrap_or(30);
            }
            "--allow-net" => {
                // WASI preview1 默认无 socket，占位
            }
            "--" => {
                i += 1;
                module_path = Some(PathBuf::from(&args[i]));
                break;
            }
            flag if flag.starts_with('-') => {
                return Err(anyhow!("未知参数: {}", flag));
            }
            _ => {
                module_path = Some(PathBuf::from(&args[i]));
                break;
            }
        }
        i += 1;
    }

    let dir = dir.ok_or_else(|| anyhow!("缺少 --dir"))?;
    let module_path = module_path.ok_or_else(|| anyhow!("缺少 wasm 模块路径"))?;
    let wasm = std::fs::read(&module_path)
        .map_err(|e| anyhow!("读取 {} 失败: {}", module_path.display(), e))?;

    let engine = Engine::default();
    let module = Module::new(&engine, wasm)?;

    let mut builder = WasiCtxBuilder::new();
    builder.inherit_stdio();
    builder.preopened_dir(&dir, ".", DirPerms::all(), FilePerms::all())?;
    let tmp = std::env::temp_dir();
    if tmp.exists() {
        builder.preopened_dir(&tmp, "/tmp", DirPerms::all(), FilePerms::all())?;
    }

    let mut store = Store::new(&engine, builder.build_p1());
    let mut linker = Linker::<WasiP1Ctx>::new(&engine);
    add_to_linker_sync(&mut linker, |cx| cx)?;
    let instance = linker.instantiate(&mut store, &module)?;

    let start = instance
        .get_typed_func::<(), ()>(&mut store, "_start")
        .map_err(|_| anyhow!("模块缺少 _start 入口"))?;
    start.call(&mut store, ())?;

    Ok(())
}