# Voice Changer Client (Tauri + Svelte)

## Dev run

1) Start server in WSL2:
```bash
cd Docker
docker compose up --build
```

2) In Windows PowerShell:
```powershell
cd client/app
npm install
cargo tauri dev
```

If the server port differs, update the URL in the UI.


