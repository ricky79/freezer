# ❄️ Freezer di cantina

Webapp per l'inventario del freezer di casa, pensata per iPhone e usabile anche **senza rete**
davanti al freezer. Le modifiche si sincronizzano col PC Linux quando si torna sotto Wi-Fi, e
ogni mattina un bot Telegram avvisa di ciò che è scaduto o sta per scadere.

- Server: Python + FastAPI + SQLite, dietro Caddy (HTTPS con certificato di casa).
- Telefono: PWA installata nella schermata Home, con coda offline.
- Design: `docs/superpowers/specs/2026-09-27-freezer-inventario-design.md`.

## Sviluppo (Windows o Linux)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Linux: .venv/bin/python
.venv/Scripts/python -m pytest                                # test del server
.venv/Scripts/python -m uvicorn --factory freezer.api:create_app --port 8765
```
Apri http://127.0.0.1:8765. Test JavaScript: `python tools/serve_tests.py` e apri
http://127.0.0.1:8766/tests/js/test.html. Le icone si rigenerano con `python tools/make_icons.py`.

## Installazione sul PC Linux

1. **Chiave per GitHub** (una volta): `ssh-keygen -t ed25519 -C freezer-pc`, poi copia
   `~/.ssh/id_ed25519.pub` in GitHub → repository `freezer` → Settings → Deploy keys → Add
   (lascia *Allow write access* spento).
2. **Scarica e installa:**
   ```bash
   sudo install -d -o "$USER" -g "$USER" /opt/freezer
   git clone git@github.com:<utente>/freezer.git /opt/freezer
   cd /opt/freezer && sudo ./deploy/install.sh
   ```
   Lo script installa Caddy, crea l'utente `freezer`, i servizi e stampa gli indirizzi da aprire
   sugli iPhone. Porte usate: 8765 (solo interna), 443 e 80. Se 443/80 fossero occupate:
   `sudo ./deploy/install.sh --https-port 8443 --http-port 8080`.
3. **Aggiornare** dopo nuove modifiche: `cd /opt/freezer && git pull && sudo ./deploy/install.sh`.

## iPhone (una volta per telefono)

In Safari, sotto il Wi-Fi di casa, apri `http://<nome-pc>.local/cert` e segui la pagina:
certificato → Impostazioni → Profilo scaricato → Installa → Generali → Info → Impostazioni
attendibilità certificati → attiva **Freezer di casa**. Poi apri `https://<nome-pc>.local` →
Condividi → **Aggiungi alla schermata Home**.

## Telegram

1. Su Telegram scrivi a **@BotFather** → `/newbot` → scegli nome e username. Copia il **token**.
2. Crea un gruppo con la famiglia, aggiungi il bot e scrivi `/start` nel gruppo.
3. Apri `https://api.telegram.org/bot<TOKEN>/getUpdates` nel browser e cerca
   `"chat":{"id":-100…`: quel numero (col meno) è il **chat id**.
4. `sudo nano /etc/freezer/freezer.env` → compila `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
5. Prova:
   `sudo -u freezer bash -c 'set -a; . /etc/freezer/freezer.env; cd /opt/freezer && .venv/bin/python -m freezer.notify --prova'`

L'avviso parte ogni giorno alle 08:30, solo se c'è qualcosa di scaduto o in scadenza entro 7
giorni (`FREEZER_WARN_DAYS`). Per cambiare orario: `sudo ./deploy/install.sh --notify-time 07:45`.

## Backup

Ogni notte alle 03:00 in `/var/lib/freezer/backups` (ultimi 14). Per ripristinarne uno:
```bash
sudo systemctl stop freezer
sudo -u freezer cp /var/lib/freezer/backups/freezer-AAAAMMGG-HHMMSS.db /var/lib/freezer/freezer.db
sudo rm -f /var/lib/freezer/freezer.db-wal /var/lib/freezer/freezer.db-shm
sudo systemctl start freezer
```

## Problemi comuni

| Sintomo | Cosa fare |
|---|---|
| L'app dice "PC non raggiungibile" in casa | `systemctl status freezer caddy`; il telefono è sul Wi-Fi di casa? |
| Safari avvisa che la connessione non è privata | Ripeti il passo "attendibilità certificati" sull'iPhone |
| L'iPhone non trova `<nome-pc>.local` | Prenota un IP fisso per il PC sul router e rilancia `sudo ./deploy/install.sh --host 192.168.1.50` (col tuo IP). Poi sugli iPhone apri il nuovo indirizzo e rimetti l'app nella Home: con un indirizzo nuovo la coda offline riparte da zero, quindi fallo sotto Wi-Fi a coda vuota. |
| Nessun messaggio Telegram | `journalctl -u freezer-notify -n 20`; il messaggio parte solo se c'è qualcosa in scadenza |
| Log dell'app | `journalctl -u freezer -n 50` |
