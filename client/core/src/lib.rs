use anyhow::{anyhow, Result};
use bytes::Bytes;
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use std::sync::{Arc, Mutex}; // Use the standard library's Mutex for synchronous contexts
use std::sync::mpsc as std_mpsc;
use std::thread::JoinHandle;
use tokio::sync::mpsc;
use tokio_tungstenite::connect_async;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, SampleRate, StreamConfig};

#[derive(Clone, Debug)]
pub struct AudioConfig {
    pub sample_rate: u32,  // 48000
    pub channels: u16,     // 1
    pub frame_size: u32,   // 480 samples (10ms)
}

// Use snake_case for fields and add the serde attribute to keep the JSON output as camelCase.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct InitMessage<'a> {
    r#type: &'a str,
    sample_rate: u32,
    channels: u16,
    format: &'a str,
    frame_size: u32,
}

pub struct StreamHandle {
    stop_tx: std_mpsc::Sender<()>,
    worker: JoinHandle<()>,
}

impl StreamHandle {
    pub async fn stop(self) -> Result<()> {
        let _ = self.stop_tx.send(());
        let _ = self.worker.join();
        Ok(())
    }
}

pub async fn start_stream(ws_url: &str, cfg: AudioConfig) -> Result<StreamHandle> {
    // Stop signal for the dedicated worker thread
    let (stop_tx, stop_rx) = std_mpsc::channel::<()>();
    let ws_url_owned = ws_url.to_string();

    // Spawn a dedicated OS thread to own CPAL streams and a single-threaded Tokio runtime
    let worker: JoinHandle<()> = std::thread::spawn(move || {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("failed to build runtime");

        rt.block_on(async move {
            // Set up audio I/O with cpal
            let host = cpal::default_host();
            let input_device = match host.default_input_device() {
                Some(d) => d,
                None => { eprintln!("No default input device"); return; }
            };
            let output_device = match host.default_output_device() {
                Some(d) => d,
                None => { eprintln!("No default output device"); return; }
            };

            // Build stream configs
            // Choose an input config with graceful fallbacks (prefer I16 mono → I16 stereo)
            let input_config = {
                let supported = match input_device.supported_input_configs() {
                    Ok(it) => it.collect::<Vec<_>>(),
                    Err(e) => { eprintln!("list input configs: {e}"); return; }
                };

                let desired_channels = [cfg.channels, 2];
                let mut pick = None;
                for &ch in &desired_channels {
                    if let Some(found) = supported
                        .iter()
                        .find(|c| c.channels() == ch && c.sample_format() == cpal::SampleFormat::I16)
                    {
                        pick = Some(found.clone());
                        break;
                    }
                }
                let range = match pick {
                    Some(r) => r,
                    None => { eprintln!("No matching input config for I16 (mono or stereo)"); return; }
                };
                let target = SampleRate(cfg.sample_rate);
                if range.min_sample_rate() <= target && target <= range.max_sample_rate() {
                    range.with_sample_rate(target).config()
                } else {
                    range.with_max_sample_rate().config()
                }
            };

            // Choose an output config with graceful fallbacks (prefer I16 mono → I16 stereo → F32 mono → F32 stereo → any)
            let (output_config, output_sample_format): (StreamConfig, SampleFormat) = {
                let supported = match output_device.supported_output_configs() {
                    Ok(it) => it.collect::<Vec<_>>(),
                    Err(e) => { eprintln!("list output configs: {e}"); return; }
                };

                let mut pick = None;
                // Preference order
                let desired_channels = [cfg.channels, 2];
                let desired_formats = [SampleFormat::I16, SampleFormat::F32];
                for &fmt in &desired_formats {
                    for &ch in &desired_channels {
                        if let Some(found) = supported
                            .iter()
                            .find(|c| c.channels() == ch && c.sample_format() == fmt)
                        {
                            pick = Some((found.clone(), fmt));
                            break;
                        }
                    }
                    if pick.is_some() { break; }
                }
                // Final fallback: first supported
                let (range, fmt) = if let Some(p) = pick {
                    p
                } else if let Some(first) = supported.first() {
                    (first.clone(), first.sample_format())
                } else {
                    eprintln!("No supported output configs available");
                    return;
                };

                let target = SampleRate(cfg.sample_rate);
                let cfg2 = if range.min_sample_rate() <= target && target <= range.max_sample_rate() {
                    range.with_sample_rate(target).config()
                } else {
                    range.with_max_sample_rate().config()
                };
                (cfg2, fmt)
            };

            // Channels between input callback and ws task
            let (frame_tx, mut frame_rx) = mpsc::channel::<Bytes>(64);
            let (play_tx, play_rx) = mpsc::channel::<Bytes>(64);
            let play_rx = Arc::new(Mutex::new(play_rx));

            // Build input stream
            let mut input_accum: Vec<i16> = Vec::with_capacity((cfg.frame_size * cfg.channels as u32) as usize);
            let input_stream = {
                let cfg_clone = cfg.clone();
                let in_channels = input_config.channels as usize;
                input_device.build_input_stream(
                    &input_config,
                    move |data: &[i16], _| {
                        // Downmix to mono if needed, keep S16
                        if in_channels == 1 {
                            input_accum.extend_from_slice(data);
                        } else {
                            for frame in data.chunks(in_channels) {
                                let mut sum: i32 = 0;
                                for &s in frame.iter() { sum += s as i32; }
                                let avg = (sum / (in_channels as i32)).clamp(i16::MIN as i32, i16::MAX as i32) as i16;
                                input_accum.push(avg);
                            }
                        }
                        let samples_per_frame = (cfg_clone.frame_size * cfg_clone.channels as u32) as usize;
                        while input_accum.len() >= samples_per_frame {
                            let chunk = input_accum.drain(..samples_per_frame).collect::<Vec<i16>>();
                            let bytes = bytemuck::cast_slice(&chunk).to_vec();
                            // Use try_send to avoid blocking the audio thread
                            let _ = frame_tx.try_send(Bytes::from(bytes));
                        }
                    },
                    move |err| {
                        eprintln!("input stream error: {err}");
                    },
                    None,
                ).expect("build_input_stream failed")
            };

            // Build output stream
            let output_stream = {
                let play_rx = play_rx.clone();
                match output_sample_format {
                    SampleFormat::I16 => {
                        output_device.build_output_stream(
                            &output_config,
                            move |output: &mut [i16], _| {
                                let channels = output_config.channels as usize;
                                let mut idx = 0usize;
                                if let Ok(mut guard) = play_rx.try_lock() {
                                    // Fill buffer with as many frames as available; duplicate mono→stereo if needed
                                    while idx < output.len() {
                                        match guard.try_recv() {
                                            Ok(bytes) => {
                                                let mono_samples: &[i16] = bytemuck::cast_slice(&bytes);
                                                for &s in mono_samples {
                                                    if channels == 1 {
                                                        if idx < output.len() { output[idx] = s; idx += 1; } else { break; }
                                                    } else {
                                                        // duplicate into all channels
                                                        for _c in 0..channels {
                                                            if idx < output.len() { output[idx] = s; idx += 1; } else { break; }
                                                        }
                                                    }
                                                }
                                            }
                                            Err(_) => {
                                                while idx < output.len() { output[idx] = 0; idx += 1; }
                                                break;
                                            }
                                        }
                                    }
                                } else {
                                    for sample in output.iter_mut() { *sample = 0; }
                                }
                            },
                            move |err| { eprintln!("output stream error: {err}"); },
                            None,
                        ).expect("build_output_stream failed")
                    }
                    SampleFormat::F32 => {
                        output_device.build_output_stream(
                            &output_config,
                            move |output: &mut [f32], _| {
                                let channels = output_config.channels as usize;
                                let mut idx = 0usize;
                                if let Ok(mut guard) = play_rx.try_lock() {
                                    while idx < output.len() {
                                        match guard.try_recv() {
                                            Ok(bytes) => {
                                                let mono_i16: &[i16] = bytemuck::cast_slice(&bytes);
                                                for &s in mono_i16 {
                                                    let v = (s as f32) / 32768.0;
                                                    if channels == 1 {
                                                        if idx < output.len() { output[idx] = v; idx += 1; } else { break; }
                                                    } else {
                                                        for _c in 0..channels {
                                                            if idx < output.len() { output[idx] = v; idx += 1; } else { break; }
                                                        }
                                                    }
                                                }
                                            }
                                            Err(_) => {
                                                while idx < output.len() { output[idx] = 0.0; idx += 1; }
                                                break;
                                            }
                                        }
                                    }
                                } else {
                                    for sample in output.iter_mut() { *sample = 0.0; }
                                }
                            },
                            move |err| { eprintln!("output stream error: {err}"); },
                            None,
                        ).expect("build_output_stream failed")
                    }
                    other => {
                        eprintln!("Unsupported output sample format: {:?}", other);
                        return;
                    }
                }
            };

            if let Err(e) = input_stream.play() { eprintln!("failed to play input stream: {e}"); return; }
            if let Err(e) = output_stream.play() { eprintln!("failed to play output stream: {e}"); return; }

            // Connect websocket and run main loop
            let (ws_stream, _resp) = match connect_async(&ws_url_owned).await {
                Ok(v) => v,
                Err(e) => { eprintln!("ws connect error: {e}"); return; }
            };
            let (mut ws_writer, mut ws_reader) = ws_stream.split();

            let init = InitMessage {
                r#type: "init",
                sample_rate: cfg.sample_rate,
                channels: cfg.channels,
                format: "S16LE",
                frame_size: cfg.frame_size,
            };
            if let Err(e) = ws_writer
                .send(tokio_tungstenite::tungstenite::Message::Text(serde_json::to_string(&init).unwrap()))
                .await
            {
                eprintln!("ws send init error: {e}");
                return;
            }

            // Reader task to forward audio to playback queue
            let reader_play_tx = play_tx.clone();
            let reader_task = tokio::spawn(async move {
                while let Some(msg) = ws_reader.next().await {
                    match msg {
                        Ok(tokio_tungstenite::tungstenite::Message::Binary(data)) => {
                            let _ = reader_play_tx.send(Bytes::from(data)).await;
                        }
                        Ok(_) => {}
                        Err(e) => { eprintln!("ws read error: {e}"); break; }
                    }
                }
            });

            // Stats accounting
            let start_time = std::time::Instant::now();
            let mut last_stats = std::time::Instant::now();
            let mut total_frames: u64 = 0;
            let mut total_bytes: u64 = 0;

            loop {
                // Stop signal from main thread
                if stop_rx.try_recv().is_ok() { break; }

                tokio::select! {
                    // Outgoing audio frames from input
                    maybe = frame_rx.recv() => {
                        if let Some(frame) = maybe {
                            total_frames += 1;
                            total_bytes += frame.len() as u64;
                            if let Err(e) = ws_writer.send(tokio_tungstenite::tungstenite::Message::Binary(frame.to_vec())).await {
                                eprintln!("ws write error: {e}");
                                break;
                            }
                        }
                    }
                    // Idle tick to let reader run
                    _ = tokio::time::sleep(std::time::Duration::from_millis(5)) => {}
                }

                if last_stats.elapsed() >= std::time::Duration::from_secs(1) {
                    let elapsed = start_time.elapsed().as_secs_f64();
                    let stats = serde_json::json!({
                        "type": "stats",
                        "elapsedSec": (elapsed * 1000.0).round() / 1000.0,
                        "frames": total_frames,
                        "bytes": total_bytes,
                    });
                    let _ = ws_writer
                        .send(tokio_tungstenite::tungstenite::Message::Text(stats.to_string()))
                        .await;
                    last_stats = std::time::Instant::now();
                }
            }

            let _ = reader_task.abort();
        });
    });

    Ok(StreamHandle { stop_tx, worker })
}
