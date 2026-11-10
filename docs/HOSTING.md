# Hosting Nyaymalaw for other advocates

Plan AN.48, piece 48f6 (owner decision D167, 10 Nov 2026), with the hosting review of the same day. What it takes to run NM on a
machine other advocates reach, as built by 48f1-48f5, and what the machine and its operator must supply. Each statement below was
checked against the code; where NM does not yet do something, it says so.

## The two processes

Run NM as two processes on one machine, sharing the same store and the same settings:

| Process | Command | What it does |
|---|---|---|
| Web server | `python -m nm.app.main --no-follow-code --host 127.0.0.1 --port 8000` | Serves the pages, takes messages and go-aheads, reads progress. Works no step itself. |
| Step worker | `python -m nm.app.step_worker` | Works every step: reading the papers, research, writing. Holds the AI calls and the law search. |

`--no-follow-code` matters: the code-following supervisor is for development. On a hosted machine an update is deployed by restarting
the processes deliberately. Keep both running with the machine's own supervisor: a systemd unit each on Linux (Restart=always), or on
Windows a service each (for example with NSSM) or a Task Scheduler task at start-up that restarts on failure.

## Settings

Both processes read the same settings (the `.env` file or the machine's environment).

| Setting | Value | Why |
|---|---|---|
| `NM_STEP_WORKER` | `separate` | The web server hands each step to the worker. Unset, one process works everything, as on the laptop. |
| `NM_STEP_WAIT_SECONDS` | `20` (default) | How long a request waits for its step before answering "working". Keep it under the proxy's request timeout. |
| `NM_STEPS_AT_ONCE` | `3` (default) | Steps at work at once on the machine. Raise it only if the graphics card, the AI account's rate limit and the processor allow. |
| `NM_STEPS_PER_ADVOCATE` | `2` (default) | Steps at work at once for one advocate, so that one cannot take every place. |
| `NM_PUBLIC_URL` | `https://<your domain>` | Where NM lives. Password-reset links are built from it and public sign-up needs it; without it no reset link goes by mail. |
| `NM_TRUSTED_ORIGINS` | `https://<your domain>` | The page's address the server accepts changes from. Behind a proxy NM otherwise compares the page with its own inner address and refuses every change as cross-site. |
| `NM_MATTER_STORE` | a folder of its own | Conversations, accounts, usage, papers and the step stores. Use a fresh folder, not the development `.nm`, which also holds test reports and logs. |
| `NM_MATTER_KEY` | a long random secret | Seals everything in the store. Without it NM makes `.nm/matter.key` once. Lose it and every conversation and paper is unreadable; it may not be the AI key (NM refuses to start if it is). |
| `NM_CLAMSCAN`, `NM_CLAMAV_DATABASE` | the ClamAV scanner and its definitions folder | Every paper is checked for malware before it is read. Without a scanner, papers are held and never read: advocates cannot send papers. |
| `NM_CORPUS_DIR`, `NM_BARE_ACTS_DIR` | the law library's folders | Default to `legal_database/vector_store` and `legal_database/raw_data/BareActs` under the checkout. |
| `FORWARDED_ALLOW_IPS` | the proxy's address | Only where the proxy is on another machine or container; NM trusts the proxy's forwarded headers from `127.0.0.1` already. |

## The web proxy in front

Put a reverse proxy (nginx, Caddy, or a tunnel such as Cloudflare's) in front of the web server for HTTPS. It must pass on three
things, or NM goes wrong in quiet ways:

- **`X-Forwarded-Proto: https`** - NM marks its sign-in cookies secure only when it knows the page came over HTTPS.
- **`X-Forwarded-For`** with the visitor's address - NM pauses sign-in after 20 wrong passwords from one address in 15 minutes (and 5
  for one account). Without the visitor's address every visitor looks like the proxy, and 20 wrong passwords from anyone pause sign-in
  for everyone.
- **`Host`** - with `NM_TRUSTED_ORIGINS` set this is belt and braces; without it, changes are refused.

Requests answer within `NM_STEP_WAIT_SECONDS` plus a few seconds, so the proxy's usual 60-second timeout is enough for everything
except the progress stream (`/api/turn-events`, server-sent events), which must not be buffered and may stay open for up to half an
hour; NM sends something at least every 2 seconds while a step works. Where a proxy blocks the stream anyway, the page asks every 2
seconds instead, so nothing breaks. An nginx example:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

location /api/turn-events {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;          # NM also says X-Accel-Buffering: no
    proxy_read_timeout 1h;
}
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 60s;
    client_max_body_size 50m;     # papers up to 16 MB each, voice notes up to 25 MB
}
```

## Accounts and email

- **Public sign-up is off** until three things hold: `NM_PUBLIC_REGISTRATION=enabled`, a mail provider that delivers to real
  mailboxes, and `NM_PUBLIC_URL` starting `https://`. Until then the server refuses sign-ups and the form says "New registration is
  unavailable while email delivery is disabled. Existing accounts can still sign in."
- **Account mail goes to a sealed outbox on the machine** by default, not to anyone's inbox. A password reset waits there until the
  operator reads it with `python operations/outbox.py --email <address>` and passes the link on.
- **Real email** needs a provider NM's outbound policy admits. The code has a Gmail sender (`NM_MAIL_PROVIDER=gmail`,
  `NM_MAIL_DELIVERY=enabled`, `NM_MAIL_SENDER`, `NM_GMAIL_TOKEN_FILE`), but the outbound policy admits no mail provider yet: enabling
  one is a decision of its own.
- **Until then, enrol each advocate yourself**: `python operations/enrol.py --id <email> --name "<name>" ...` prints a password once;
  hand it over safely. Invitations (`operations/invite.py`) need a client that sends the invitation header; the page cannot accept
  one yet.
- **The first admin** is made with `python operations/admin.py make-admin --account <email> --operator <you> --reason "first admin"`;
  allowances and user types are then set in the Admin area.

## The law library and its models

Copy `legal_database/` to the machine, with the two search models' weights it holds (`BAAI/bge-large-en-v1.5` and
`BAAI/bge-reranker-v2-m3`, loaded from local files only - nothing is fetched at run time). A graphics card is used when present;
without one the search runs on the processor, which works but makes research slower.

## Installing

Use Python 3.11 or later and install from `requirements-hosting.txt`: every package the server needs at run time, pinned to the
versions NM is run and tested with (`pyproject.toml` names only the lowest versions, so installing from it can pull releases nobody
has run NM with). The list is written by `development_environment/developer_tooling/hosting_requirements.py` from the working
environment, and a test says when an upgrade there has left it behind.

```
pip install -r requirements-hosting.txt
```

Torch is pinned by version only, because its build is the machine's choice: on Linux the standard package carries the graphics-card
build; on Windows, for a graphics card, install torch 2.6.0 from the PyTorch index's CUDA 12.4 build first, then the list. ClamAV is
installed separately. The Anthropic adapter's package is not on the list; hosting on the OpenAI account does not need it.

## Backups

- Back up the whole `NM_MATTER_STORE` folder: conversations, papers, accounts, usage, the outbox and the step stores - everything in it
  is sealed.
- Keep `NM_MATTER_KEY` (or `.nm/matter.key`) **apart from** the backups and as safely: a backup without its key cannot be read, and the
  key with a backup opens everything.
- Test a restore on another machine before relying on it.

## Restarts and updates

- **Restarting the web server** stops no step: the worker goes on, and the pages pick up again when the server is back.
- **Restarting the worker** stops the steps at work. At its start it takes each one up again by itself, from the work already saved,
  as long as the advocate's sign-in still holds; a message that had not yet begun was never kept and is said as before ("NM was
  restarted before your message reached it"), and the page's own draft lets the advocate send it again.
- **To update NM**: stop the worker (it is safe at any time), stop the web server, update the code, start the worker, start the web
  server. Steps that were at work are taken up again by the worker.

## Logs

- The outbound-data log (`.nm/egress.log` under the checkout, whatever `NM_MATTER_STORE` says) records every send to an outside
  service and only ever grows (174 MB on the development machine): rotate it with the machine's own tool (logrotate, or a scheduled
  task).
- Each process writes its warnings to its own console; let the supervisor keep them.

## Checked before handing over

- `python -m nm.app.main --check` prints the health and exits; it must say `"runtime": "ready"`.
- With both processes running, `GET /api/health` must say `"steps": {"mode": "separate", "worker": "alive", ...}`; with one process,
  `"mode": "inside"`. Either way it says how many steps wait and how many are at work - counts only, never whose or what. An outside
  monitor that reads it can say when the worker stops.
- The drills (`development_environment/developer_tooling/step_drills.py`) run offline on a throwaway store under a short temporary
  path, with the stand-in models the tests use - no paid call, never the installation's own conversations or accounts:
  - `restart`: a step whose process is killed in the middle is taken up by the next start, by itself, to the same result as a run
    that was never interrupted;
  - `split`: with the web server and the worker as two processes, the web server is killed and started again in the middle of a
    step, which the worker finishes;
  - `load`: several advocates' matters at once stay within the limits, every step finishes, and the pages answer meanwhile;
  - `stream`: through a real server, what a step is doing reaches the page as it changes, until the step's last word.

## Not covered here

- Choosing the machine, the domain and its HTTPS certificate.
- The AI account's own limits: three steps at once each make several calls; check the account's rate and spending limits.
- The terms advocates accept and how client papers are handled outside NM.
