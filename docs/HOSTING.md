# Hosting Nyaymalaw for other advocates

Plan AN.48, piece 48f6 (owner decision D167, 10 Nov 2026). What it takes to run NM on a machine other advocates reach, as built by
48f1-48f5. It does not cover choosing the machine, its graphics card, putting the held law library on it, HTTPS certificates, backups
or real email for account messages; those are listed at the end.

## The two processes

Run NM as two processes on one machine, sharing the same `.nm` store and the same settings:

| Process | Command | What it does |
|---|---|---|
| Web server | `python -m nm.app.main --no-follow-code --host 127.0.0.1 --port 8000` | Serves the pages, takes messages and go-aheads, reads progress. Works no step itself. |
| Step worker | `python -m nm.app.step_worker` | Works every step: reading the papers, research, writing. Holds the AI calls and the law search. |

Both read the same settings (the `.env` file or the machine's environment). Set in both:

| Setting | Value | Why |
|---|---|---|
| `NM_STEP_WORKER` | `separate` | The web server hands each step to the worker. Unset, one process works everything, as on the laptop. |
| `NM_STEP_WAIT_SECONDS` | `20` (default) | How long a request waits for its step before answering "working". Keep it under the proxy's request timeout. |
| `NM_STEPS_AT_ONCE` | `3` (default) | Steps at work at once on the machine. Raise it only if the graphics card, the AI account's rate limit and the processor allow. |
| `NM_STEPS_PER_ADVOCATE` | `2` (default) | Steps at work at once for one advocate, so that one cannot take every place. |

`--no-follow-code` matters: the code-following supervisor is for development. On a hosted machine an update is deployed by restarting
the processes deliberately.

## Restarts and updates

- **Restarting the web server** stops no step: the worker goes on, and the pages pick up again when the server is back.
- **Restarting the worker** stops the steps at work. At its start it takes each one up again by itself, from the work already saved,
  as long as the advocate's sign-in still holds; a message that had not yet begun was never kept and is said as before ("NM was
  restarted before your message reached it"), and the page's own draft lets the advocate send it again.
- **To update NM**: stop the worker (it is safe at any time), stop the web server, update the code, start the worker, start the web
  server. Steps that were at work are taken up again by the worker.
- `GET /api/health` says whether the worker is there and how many steps wait and work (`steps`).

Keep both processes running with the machine's own supervisor: a systemd unit each on Linux (Restart=always), or on Windows a
service each (for example with NSSM) or a Task Scheduler task at start-up that restarts on failure.

## The web proxy in front

Put a reverse proxy (nginx, Caddy, or a tunnel such as Cloudflare's) in front of the web server for HTTPS. Two things matter:

1. **Requests**: NM answers every request within `NM_STEP_WAIT_SECONDS` plus a few seconds, so the proxy's usual 60-second timeout
   is enough for everything except the progress stream.
2. **The progress stream** (`/api/turn-events`, server-sent events): it must not be buffered, and it may stay open for up to half an
   hour. NM sends something at least every 2 seconds while a step works. Where a proxy blocks the stream anyway, the page falls back
   to asking every 2 seconds, so nothing breaks; it is only less immediate.

An nginx example:

```nginx
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
    client_max_body_size 50m;     # papers uploaded with a message
}
```

## Checked before handing over

- `python -m nm.app.main --check` prints the health and exits; it must say `"runtime": "ready"`.
- With both processes running, `GET /api/health` must say `"steps": {"mode": "separate", "worker": "alive", ...}`; with one process,
  `"mode": "inside"`. Either way it says how many steps wait and how many are at work - counts only, never whose or what.
- The drills (`development_environment/developer_tooling/step_drills.py`) run offline on a throwaway store under a short temporary
  path, with the stand-in models the tests use - no paid call, never the installation's own conversations or accounts:
  - `restart`: a step whose process is killed in the middle is taken up by the next start, by itself, to the same result as a run
    that was never interrupted;
  - `split`: with the web server and the worker as two processes, the web server is killed and started again in the middle of a
    step, which the worker finishes;
  - `load`: several advocates' matters at once stay within the limits, every step finishes, and the pages answer meanwhile;
  - `stream`: through a real server, what a step is doing reaches the page as it changes, until the step's last word.

## Not covered here

- The hosting machine itself, its graphics card for the law search, and the held law library (`legal_database/`) on it.
- HTTPS certificates and the domain name.
- Backups of `.nm` (conversations, accounts, usage) - and a test that a backup can be restored.
- Real email for account messages (sign-up confirmations, password resets); the local outbox is for development only.
- The outbound-data log (`.nm/egress.log`), which only ever grows; rotate it.
- Sign-ups and accounts for the other advocates, and their usage allowances (the Admin area).
