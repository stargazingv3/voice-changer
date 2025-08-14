#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::State;
use tokio::sync::Mutex;
use voice_changer_core::{start_stream, AudioConfig, StreamHandle};

struct AppState {
    handle: Option<StreamHandle>,
}

impl AppState {
    fn new() -> Self {
        Self { handle: None }
    }
}

#[tauri::command]
async fn start_stream_cmd(state: State<'_, Mutex<AppState>>, url: String) -> Result<(), String> {
    let mut guard = state.lock().await;
    if guard.handle.is_some() {
        return Ok(());
    }
    let cfg = AudioConfig { sample_rate: 48000, channels: 1, frame_size: 480 };
    let handle = start_stream(&url, cfg).await.map_err(|e| e.to_string())?;
    guard.handle = Some(handle);
    Ok(())
}

#[tauri::command]
async fn stop_stream_cmd(state: State<'_, Mutex<AppState>>) -> Result<(), String> {
    let mut guard = state.lock().await;
    if let Some(handle) = guard.handle.take() {
        handle.stop().await.map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(Mutex::new(AppState::new()))
        .invoke_handler(tauri::generate_handler![start_stream_cmd, stop_stream_cmd])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}


