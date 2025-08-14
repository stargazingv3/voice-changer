<script lang="ts">
  import { invoke } from "@tauri-apps/api/core";
  import { onMount } from "svelte";

  let serverUrl = "ws://localhost:8000/stream/audio";
  let running = false;
  let errorMsg = "";

  async function start() {
    errorMsg = "";
    try {
      await invoke("start_stream_cmd", { url: serverUrl });
      running = true;
    } catch (e) {
      errorMsg = String(e);
    }
  }

  async function stop() {
    try {
      await invoke("stop_stream_cmd");
      running = false;
    } catch (e) {
      errorMsg = String(e);
    }
  }

  onMount(() => {
    // no-op
  });
</script>

<main style="font-family: sans-serif; padding: 1rem;">
  <h1>Voice Changer</h1>

  <label>Server URL</label>
  <input style="display:block; width:100%; max-width: 520px;" bind:value={serverUrl} />

  <div style="margin-top: 1rem; display:flex; gap: .5rem;">
    {#if !running}
      <button on:click={start}>Start</button>
    {:else}
      <button on:click={stop}>Stop</button>
    {/if}
  </div>

  {#if errorMsg}
    <pre style="color:crimson; margin-top:1rem;">{errorMsg}</pre>
  {/if}

  <p style="margin-top:1rem;">MVP: capture → WS → echo → play</p>
</main>


