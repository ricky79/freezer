# Freezer di cantina — Design

Data: 2026-09-27
Stato: in revisione

## 1. Obiettivo

Una webapp per tenere l'inventario del freezer in cantina, usata da tutta la famiglia
dai propri iPhone. Permette di:

- registrare ciò che si mette dentro (descrizione, tipo, quantità, scadenza);
- togliere ciò che si prende (anche solo in parte);
- essere avvisati di ciò che è scaduto o sta per scadere.

### Criteri di successo

- Davanti al freezer, **senza rete**, si può consultare l'inventario, aggiungere e prendere.
- Tornati sotto Wi-Fi, le modifiche di tutti i telefoni confluiscono in un unico inventario
  senza perdite né doppi conteggi.
- Ogni mattina, se c'è qualcosa di scaduto o in scadenza, arriva un messaggio nel gruppo
  Telegram di famiglia.
- Dopo l'installazione iniziale nessuno deve fare manutenzione.

### Vincoli

| Vincolo | Conseguenza |
|---|---|
| Più utenti, più iPhone, dati condivisi | Serve un server con i dati centrali |
| Server = PC Linux Mint 22.2, x86_64, Python 3.12.3, 3,8 GB RAM, sempre acceso | Stack leggero: Python + SQLite, niente Docker |
| In cantina il Wi-Fi è debole o assente | App offline-first con coda di operazioni e sincronizzazione |
| Solo iPhone | L'offline richiede una PWA installata in Home servita in HTTPS |
| Porta 5000 già occupata da un'altra webapp | L'app usa la porta interna 8765 (configurabile) |
| Codice su GitHub privato | Il PC Linux scarica il codice con `git` tramite deploy key in sola lettura |

### Fuori ambito (YAGNI)

Login e utenti, chi-ha-fatto-cosa, storico dei movimenti, statistiche, più freezer,
posizione/cassetto, codici a barre, notifiche push iOS, accesso da fuori casa.

## 2. Architettura

```
 iPhone (PWA in Home)                         PC Linux Mint
┌───────────────────────────┐   HTTPS    ┌────────────────────────────────────┐
│ UI (HTML/CSS/JS vanilla)  │  :443      │ Caddy  (tls internal, CA di casa)  │
│ copia inventario + coda   │──────────► │   │ reverse proxy                  │
│ (localStorage)            │            │   ▼                                │
│ service worker (offline)  │            │ FastAPI/uvicorn 127.0.0.1:8765     │
└───────────────────────────┘            │   │                                │
                                         │   ▼                                │
                                         │ SQLite /var/lib/freezer/freezer.db │
                                         │                                    │
                                         │ timer systemd:                     │
                                         │  • 08:30 notify → api.telegram.org │
                                         │  • 03:00 backup del database       │
                                         └────────────────────────────────────┘
```

- **Frontend:** file statici, JavaScript vanilla a moduli ES, nessuna build, nessun Node.
- **Backend:** Python 3.12, FastAPI + uvicorn, SQLite (modulo `sqlite3` della libreria standard).
  Le chiamate a Telegram usano `urllib` della libreria standard.
- **HTTPS:** Caddy con `tls internal`: genera una propria CA radice (validità 10 anni) e rinnova
  da solo i certificati del sito. La CA radice va installata una volta su ogni iPhone.
- **Nome in rete:** `https://<nomepc>.local`, annunciato da avahi (attivo di default su Mint).
  Non serve un IP fisso.
- **Nessuna autenticazione:** uvicorn ascolta solo su 127.0.0.1; Caddy è raggiungibile solo
  dalla rete di casa. Il router non inoltra porte verso il PC.

## 3. Modello dei dati

### 3.1 Catalogo (fonte unica: server)

Il catalogo è definito solo in Python (`freezer/catalog.py`) e inviato al telefono insieme
all'inventario, che lo tiene in cache. Così server e client non possono divergere.

**Tipi** (codice → etichetta):
`carne` Carne · `pesce` Pesce · `verdure` Verdure · `frutta` Frutta · `sughi` Sughi ·
`piatti_pronti` Piatti pronti · `pane_pizza` Pane e pizza · `dolci` Dolci · `altro` Altro

**Unità** (codice → singolare / plurale):

| Codice | Singolare | Plurale |
|---|---|---|
| `pezzi` | pezzo | pezzi |
| `buste` | busta | buste |
| `porzioni` | porzione | porzioni |
| `vaschette` | vaschetta | vaschette |
| `barattoli_piccoli` | barattolo piccolo | barattoli piccoli |
| `barattoli_grandi` | barattolo grande | barattoli grandi |
| `grammi` | g | g |

Formattazione: `1 busta`, `3 buste`, `2 barattoli grandi`, `500 g`.

### 3.2 Tabelle SQLite

**`lots`**: un lotto = una cosa messa dentro in un momento, con una sua scadenza.
Due confezioni uguali con scadenze diverse sono due lotti.

| Colonna | Tipo | Note |
|---|---|---|
| `id` | TEXT PK | UUID generato dal telefono |
| `description` | TEXT NOT NULL | 1–100 caratteri, spazi iniziali/finali rimossi |
| `category` | TEXT NOT NULL | codice del catalogo |
| `quantity` | INTEGER NOT NULL | ≥ 0 |
| `unit` | TEXT NOT NULL | codice del catalogo |
| `expiry` | TEXT NOT NULL | `YYYY-MM-DD` |
| `status` | TEXT NOT NULL | `active` · `consumed` (arrivato a 0) · `deleted` (eliminato) |
| `created_at` | TEXT NOT NULL | ISO 8601, ora del server all'applicazione dell'operazione |
| `updated_at` | TEXT NOT NULL | ISO 8601 |

I lotti non vengono mai cancellati fisicamente: `consumed` e `deleted` servono a ignorare in modo
pulito operazioni arrivate in ritardo e ad alimentare i suggerimenti.

**`applied_ops`**: registro delle operazioni già applicate (idempotenza).

| Colonna | Tipo |
|---|---|
| `op_id` | TEXT PK |
| `applied_at` | TEXT NOT NULL |

### 3.3 Stato di scadenza

`giorni = expiry − oggi` (data locale, fuso Europe/Rome). `warn_days` configurabile, default 7.

| Condizione | Stato | Testo |
|---|---|---|
| giorni < 0 | 🔴 `expired` | "scaduto da N giorni" / "scaduto ieri" |
| 0 ≤ giorni ≤ warn_days | 🟠 `expiring` | "oggi" / "domani" / "tra N giorni" |
| giorni > warn_days | `ok` | "tra N giorni" |

La stessa regola esiste in Python (notifiche) e in JS (interfaccia), ognuna con i propri test.

## 4. Operazioni e sincronizzazione

### 4.1 Operazioni

Ogni azione dell'utente diventa un'operazione con un `op_id` (UUID) generato dal telefono.
Il campo `at` (ora del telefono) è solo informativo: l'ordine di applicazione è quello di arrivo
al server.

```jsonc
{"op_id": "…", "type": "add",    "at": "…", "lot": {"id": "…", "description": "Ragù", "category": "sughi", "quantity": 2, "unit": "barattoli_grandi", "expiry": "2027-03-27"}}
{"op_id": "…", "type": "take",   "at": "…", "lot_id": "…", "amount": 1}
{"op_id": "…", "type": "edit",   "at": "…", "lot_id": "…", "fields": {"quantity": 3, "expiry": "2027-01-10"}}
{"op_id": "…", "type": "delete", "at": "…", "lot_id": "…"}
```

### 4.2 Regole di applicazione (server, `freezer/ops.py`)

Le regole sono funzioni pure su una connessione SQLite, applicate in una transazione per richiesta.

| Caso | Esito |
|---|---|
| `op_id` già in `applied_ops` | `duplicate`, nessun effetto |
| `add` valida, `lot.id` nuovo | lotto creato `active` → `applied` |
| `add` con `lot.id` già esistente | `ignored` |
| `take` su lotto `active` | `quantity = max(0, quantity − amount)`; se 0 → `consumed` → `applied` |
| `take` su lotto `consumed`/`deleted`/inesistente | `ignored` |
| `edit` su lotto `active` | applica solo i campi presenti → `applied` (ultima arrivata vince) |
| `edit` su lotto non `active` | `ignored` |
| `delete` su lotto `active` | `deleted` → `applied` |
| `delete` su lotto non `active` | `ignored` |
| operazione malformata (tipo sconosciuto, campi non validi) | `invalid`, registrata nel log del server |

Validazioni: `quantity` intero 1–99999 in `add` e `edit` (per azzerare si usa "Prendi tutto" o
"Elimina"); `amount` intero ≥ 1; `category`/`unit` presenti nel catalogo; `expiry` data valida;
`description` 1–100 caratteri dopo il trim.

Ogni operazione con esito `applied`, `ignored` o `invalid` viene registrata in `applied_ops`,
così un reinvio non la rivaluta.

### 4.3 API

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/inventory` | Istantanea |
| `POST` | `/api/sync` | Corpo `{"ops": [...]}` (max 500) → `{"results": [{"op_id", "status"}], ...istantanea}` |
| `GET` | `/` e file statici | Frontend da `web/` |

**Istantanea:**
```jsonc
{
  "server_time": "2026-09-27T18:32:00+02:00",
  "warn_days": 7,
  "catalog": {"categories": [...], "units": [...]},
  "lots": [ /* solo lotti active, ordinati per expiry e descrizione */ ],
  "suggestions": [ {"description": "Ragù della nonna", "category": "sughi", "unit": "barattoli_grandi"} ]
}
```
`suggestions`: descrizioni distinte (senza distinzione maiuscole/minuscole) dei lotti `active` e
`consumed`, con tipo e unità dell'uso più recente, ordinate dalla più recente; massimo 200.

`/api/sync` risponde sempre 200 se il corpo è JSON ben formato, anche con operazioni `invalid`,
così una singola operazione sbagliata non blocca la coda. Corpo malformato → 400.

### 4.4 Lato telefono

Stato in `localStorage` (ogni accesso protetto da try/catch):

- `freezer.snapshot`: ultima istantanea ricevuta;
- `freezer.queue`: operazioni non ancora confermate;
- `freezer.lastSync`: data e ora dell'ultima sincronizzazione riuscita.

**Vista mostrata = istantanea + operazioni in coda applicate localmente** con le stesse regole
del server (`web/store.js`, logica pura e testata). Così ogni azione è visibile subito anche offline.

**Ciclo di sincronizzazione (`web/sync.js`):**
1. Prende le operazioni in coda al momento dell'invio (le altre aggiunte nel frattempo restano).
2. `POST /api/sync` con timeout di 5 s.
3. Se ok: rimuove dalla coda le operazioni inviate, salva la nuova istantanea, aggiorna `lastSync`,
   ridisegna.
4. Se fallisce (rete assente, timeout, errore 5xx): la coda resta intatta; nuovo tentativo più tardi.

Solo una sincronizzazione alla volta. Attivazioni: apertura dell'app, evento `online`, ritorno in
primo piano (`visibilitychange`), dopo ogni azione, e ogni 30 s finché la coda non è vuota.

**Riga di stato:**
- `✓ Aggiornato alle 18:32` (coda vuota, ultima sync riuscita);
- `⏳ 3 modifiche da inviare` (coda non vuota);
- `⚠ PC non raggiungibile · dati del 25/09 18:32` (ultimo tentativo fallito).

**Service worker (`web/sw.js`):** cache-first per l'interfaccia (HTML, CSS, JS, icone, manifest),
con nome cache versionato; le richieste `/api/*` vanno sempre in rete, mai in cache.
Alla nuova versione: `skipWaiting` + `clients.claim`, e la pagina si ricarica. Lo stato è in
`localStorage` e non va perso.

**Primo avvio:** serve la rete (per installare l'app e ricevere catalogo e inventario), cosa già
garantita dall'installazione fatta in casa.

## 5. Interfaccia (italiano, pensata per iPhone)

### 5.1 Inventario (schermata principale)
- In alto la riga di stato della sincronizzazione.
- Fascia di avviso `🔴 1 scaduto · 🟠 3 in scadenza`, visibile solo se c'è qualcosa: toccandola
  si attiva o disattiva il filtro "solo scaduti e in scadenza".
- Ricerca per descrizione, che ignora maiuscole e accenti.
- Filtri rapidi per tipo, a scelta singola: "Tutti" + tipi presenti in inventario.
- Elenco ordinato per scadenza e poi per descrizione. Ogni riga mostra descrizione, quantità
  formattata, testo della scadenza + data `gg/mm`, colore di stato e pulsante **Prendi**.
- Tocco sulla riga → dettaglio con **Modifica** ed **Elimina**.
- Pulsante fisso **＋ Aggiungi**.
- Inventario vuoto: messaggio "Il freezer è vuoto" + invito ad aggiungere.

### 5.2 Prendi
- Pannello con descrizione e quantità attuale.
- Unità a conteggio: stepper −/+ (default 1, massimo = quantità attuale) e pulsante **Tutto**.
- Grammi: campo numerico (tastiera numerica), con validazione tra 1 e quantità attuale, e
  pulsante **Tutto**.
- Conferma → operazione `take`.

### 5.3 Aggiungi / Modifica
- Stesso modulo; in modifica è precompilato.
- **Descrizione** con suggerimenti: scegliendone uno si compilano tipo e unità.
- **Tipo** e **Unità**: selettori.
- **Quantità**: stepper per le unità a conteggio, campo numerico per i grammi.
- **Scadenza**: selettore data nativo + pulsanti rapidi `+1 mese`, `+3 mesi`, `+6 mesi` da oggi.
- Validazione in pagina con messaggi in italiano prima di mettere l'operazione in coda.

### 5.4 Elimina
Conferma dentro l'app (secondo tocco su "Conferma eliminazione"), senza le finestre di sistema.

### 5.5 Pagina "Installa certificato"
Servita da Caddy in HTTP semplice su `http://<nomepc>.local/cert`, perché prima di installare il
certificato l'HTTPS non è ancora attendibile. Contiene:
1. pulsante per scaricare `root.crt` (Content-Type `application/x-x509-ca-cert`);
2. passaggi illustrati: Impostazioni → Profilo scaricato → Installa → Generali → Info →
   Impostazioni attendibilità certificati → attivare;
3. link a `https://<nomepc>.local` e istruzioni per "Condividi → Aggiungi alla schermata Home".

## 6. Avvisi Telegram

- `python -m freezer.notify` avviato da un timer systemd, ogni giorno alle 08:30
  (`Persistent=true`: se il PC era spento, parte all'accensione).
- Considera i lotti `active` scaduti o in scadenza (§3.3). **Se non ce ne sono, non invia nulla.**
- Messaggio (testo semplice, `parse_mode` non usato per evitare problemi di escape):
  ```
  ❄️ Freezer · 27/09
  🔴 Scaduti
  • Ragù della nonna: 2 barattoli grandi (dal 20/09)
  🟠 In scadenza
  • Piselli: 3 buste (tra 3 giorni, 30/09)
  ```
  Sezioni omesse se vuote; ordine per scadenza.
- Invio: `POST https://api.telegram.org/bot<TOKEN>/sendMessage` con `chat_id`, timeout di 15 s.
  In caso di errore scrive nel log (journald) ed esce con codice ≠ 0; nessun nuovo tentativo in
  giornata.
- La costruzione del messaggio è una funzione pura, testata separatamente dall'invio.
- Se `TELEGRAM_BOT_TOKEN` o `TELEGRAM_CHAT_ID` mancano: messaggio nel log e uscita senza errore
  (così l'app si può installare anche prima di configurare Telegram).

## 7. Configurazione

File `/etc/freezer/freezer.env` (permessi 640, proprietario root:freezer):

```
FREEZER_DB_PATH=/var/lib/freezer/freezer.db
FREEZER_PORT=8765
FREEZER_WARN_DAYS=7
FREEZER_TZ=Europe/Rome
FREEZER_BACKUP_DIR=/var/lib/freezer/backups
FREEZER_BACKUP_KEEP=14
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

L'orario della notifica si cambia nel timer systemd (`install.sh` lo accetta come parametro).

## 8. Installazione e aggiornamento sul PC Linux

**Disposizione:**
- codice: `/opt/freezer` (clone git) con venv in `/opt/freezer/.venv`;
- dati: `/var/lib/freezer/` (database + backup), proprietà dell'utente di sistema `freezer`.

**Unità systemd:**
- `freezer.service`: `uvicorn freezer.api:app --host 127.0.0.1 --port ${FREEZER_PORT}`,
  `Restart=on-failure`, eseguito come utente `freezer`;
- `freezer-notify.service` + `.timer` (08:30);
- `freezer-backup.service` + `.timer` (03:00): `python -m freezer.backup` usa l'API di backup
  di SQLite e tiene gli ultimi `FREEZER_BACKUP_KEEP` file.

**Caddy** (pacchetto ufficiale da apt): Caddyfile generato da un template con il nome host.
- Blocco `https://<nomepc>.local` con `tls internal` e reverse proxy verso `127.0.0.1:8765`.
- Blocco `http://<nomepc>.local` che serve `/cert` e `/cert/root.crt` (la CA radice di Caddy) e
  reindirizza tutto il resto in HTTPS.

**`deploy/install.sh`** (idempotente: si usa anche per gli aggiornamenti):
1. verifica di essere root e che `avahi-daemon` sia attivo;
2. verifica che le porte 8765, 80 e 443 siano libere o già usate da freezer/Caddy;
   altrimenti si ferma spiegando il problema (vedi §10);
3. installa Caddy e python3-venv se mancano; crea l'utente `freezer` e le cartelle;
4. crea o aggiorna il venv e installa `requirements.txt`;
5. crea `/etc/freezer/freezer.env` dall'esempio **solo se non esiste**;
6. installa o aggiorna le unità systemd e il Caddyfile, poi `daemon-reload`, `enable --now`, `reload caddy`;
7. stampa gli indirizzi da aprire sugli iPhone.

**Aggiornamento:** `cd /opt/freezer && sudo git pull && sudo ./deploy/install.sh`.

**Accesso a GitHub dal PC:** deploy key SSH in sola lettura generata sul PC Linux e aggiunta al
repository privato. Il README spiega i passaggi.

## 9. Struttura del repository

```
freezer/
├── freezer/              # pacchetto Python
│   ├── __init__.py
│   ├── catalog.py        # tipi e unità
│   ├── config.py         # lettura variabili d'ambiente
│   ├── db.py             # schema, connessione, query istantanea/suggerimenti
│   ├── ops.py            # validazione e applicazione operazioni
│   ├── expiry.py         # stato di scadenza
│   ├── api.py            # FastAPI: /api/inventory, /api/sync, statici
│   ├── notify.py         # messaggio Telegram (costruzione + invio)
│   └── backup.py         # backup + rotazione
├── web/                  # frontend statico
│   ├── index.html
│   ├── style.css
│   ├── app.js            # interfaccia (rendering, eventi)
│   ├── store.js          # istantanea + coda + applicazione locale (puro)
│   ├── sync.js           # rete e ciclo di sincronizzazione
│   ├── expiry.js         # stato di scadenza e testi (puro)
│   ├── format.js         # quantità/date formattate (puro)
│   ├── sw.js
│   ├── manifest.webmanifest
│   └── icons/
├── deploy/
│   ├── install.sh
│   ├── Caddyfile.template
│   ├── cert.html         # pagina "Installa certificato"
│   ├── freezer.env.example
│   └── systemd/          # service e timer
├── tests/
│   ├── test_ops.py
│   ├── test_api.py
│   ├── test_expiry.py
│   ├── test_notify.py
│   ├── test_backup.py
│   └── js/               # test.html + test dei moduli puri
├── requirements.txt
├── requirements-dev.txt
└── README.md             # installazione, Telegram, iPhone, aggiornamento
```

## 10. Rischi e punti da verificare

| Rischio | Mitigazione |
|---|---|
| Le porte 80/443 sul PC Linux sono già usate (es. da un server web dell'altra webapp) | Da verificare prima dell'installazione con `sudo ss -tlnp`. Alternativa pronta: Caddy su 8443 (HTTPS) e 8080 (pagina certificato), indirizzo `https://<nomepc>.local:8443`. Le porte sono parametri di `install.sh`. |
| L'iPhone non risolve `<nomepc>.local` | avahi verificato da `install.sh`; in alternativa si usa l'IP con prenotazione DHCP sul router, aggiungendo l'IP come secondo indirizzo del sito nel Caddyfile (così il certificato copre anche l'IP). |
| Nuovo telefono in famiglia | La pagina `/cert` rende la procedura ripetibile in 2 minuti. |
| Perdita del database | Backup notturni, 14 copie. |
| Modifiche contemporanee allo stesso campo | Vince l'ultima arrivata al server; caso raro, accettato. |

## 11. Test

**Python (pytest, eseguiti su Windows in sviluppo):**
- `test_ops.py`: ogni riga della tabella §4.2, inclusi prelievi concorrenti (5 − 2 − 1 = 2),
  prelievo oltre la quantità (→ 0, `consumed`), reinvio della stessa coda (nessun doppio effetto),
  validazioni.
- `test_api.py`: `/api/inventory` e `/api/sync` con TestClient su un database temporaneo;
  forma dell'istantanea; corpo malformato → 400; limite di 500 operazioni.
- `test_expiry.py`: confini (ieri, oggi, domani, warn_days, warn_days + 1).
- `test_notify.py`: testo del messaggio (sezioni, plurali, nessun messaggio se vuoto); invio con
  `urllib` finto; configurazione mancante.
- `test_backup.py`: backup valido e rotazione a N file.

**JavaScript (pagina `tests/js/test.html` aperta nel browser, senza Node):**
`store.js` (applicazione locale di tutte le operazioni, stesse regole del server, rimozione dalla
coda delle sole operazioni inviate), `expiry.js`, `format.js`.

**End-to-end in Chrome (in sviluppo, `localhost`):** aggiungere, prendere, modificare, eliminare;
server spento → le operazioni vanno in coda e la riga di stato lo mostra; server riacceso →
coda svuotata e inventario coerente; due schede che prendono dallo stesso lotto offline →
quantità finale corretta.

**Collaudo sul PC Linux e su iPhone reale:** installazione con `install.sh`, installazione del
certificato, app in Home, modalità aereo in cantina, messaggio Telegram di prova.
