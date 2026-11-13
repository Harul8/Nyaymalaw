# Hosting Nyaymalaw for other advocates

Plan AN.48, piece 48f6 (owner decision D167, 10 Nov 2026), with the hosting review of the same day and the owner's decisions it
left (D168: Gmail sends account mail; D169: the outgoing-data log kept a year). What it takes to run NM on a
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
| `NM_PROVIDER_REQUESTS_AT_ONCE` | `16` (default) | Requests each process has out to the AI provider at once. A refusal for the account's rate is waited out as long as the provider says, up to a minute a call; lower this where refusals are frequent. |
| `NM_PUBLIC_URL` | `https://<your domain>` | Where NM lives. Password-reset links are built from it and public sign-up needs it; without it no reset link goes by mail. |
| `NM_TRUSTED_ORIGINS` | `https://<your domain>` | The page's address the server accepts changes from. Behind a proxy NM otherwise compares the page with its own inner address and refuses every change as cross-site. |
| `NM_MATTER_STORE` | a folder of its own | Conversations, accounts, usage, papers and the step stores. Use a fresh folder, not the development `.nm`, which also holds test reports and logs. |
| `NM_MATTER_KEY` | a long random secret | Seals everything in the store. Without it NM makes `.nm/matter.key` once. Lose it and every conversation and paper is unreadable; it may not be the AI key (NM refuses to start if it is). |
| `NM_MATTER_KEY_FILE` | a file outside the code and the store | Instead of `NM_MATTER_KEY`: a file that holds the secret, so it can be kept apart from the code, the data and the backups. NM reads it and never writes it. NM refuses to start if the file is missing or empty, or if both this and `NM_MATTER_KEY` are set. |
| `NM_EGRESS_LOG_DIR` | a folder of its own | Where the outgoing-data log is kept. Unset, it is `.nm` under the code, which a deployment replaces. See "Logs". |
| `NM_CLAMSCAN`, `NM_CLAMAV_DATABASE` | the ClamAV scanner and its definitions folder | Every paper is checked for malware before it is read. Without a scanner, papers are held and never read: advocates cannot send papers. |
| `NM_CORPUS_DIR`, `NM_BARE_ACTS_DIR` | the law library's folders | Default to `legal_database/vector_store` and `legal_database/raw_data/BareActs` under the checkout. |
| `NM_MAIL_PROVIDER`, `NM_MAIL_DELIVERY`, `NM_MAIL_SENDER`, `NM_GMAIL_APP_PASSWORD_FILE` | `gmail`, `enabled`, the sending address, the app password's file | Account email through Gmail; see "Sending account email with Gmail" below. Unset, account mail waits in the machine's own outbox. |
| `NM_PUBLIC_REGISTRATION` | `enabled` | Opens public sign-up, once mail reaches real mailboxes and `NM_PUBLIC_URL` is set. Unset, only accounts the operator enrols exist. |
| `NM_EGRESS_LOG_KEEP_DAYS` | `365` (default) | How many days the outgoing-data log is kept. A longer period may be set; nothing under 180 days is taken. See "Logs". |
| `FORWARDED_ALLOW_IPS` | the proxy's address | Only where the proxy is on another machine or container; NM believes the proxy's forwarded headers from this machine (`127.0.0.1` and `::1`) already, and says at start-up whom it believes. Never `*`: a visitor could then write their own address, and the sign-in limits count by it. |

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
- **Real email goes through Gmail** (owner decision D168, 10 Nov 2026), set up as below.
- **Until then, enrol each advocate yourself**: `python operations/enrol.py --id <email> --name "<name>" ...` prints a password once;
  hand it over safely. Invitations (`operations/invite.py`) need a client that sends the invitation header; the page cannot accept
  one yet.
- **The first admin** is made with `python operations/admin.py make-admin --account <email> --operator <you> --reason "first admin"`;
  allowances and user types are then set in the Admin area.

### Sending account email with Gmail

NM sends two kinds of email, and only these: the six-digit code that confirms a new account's address, and the link that sets a new
password. Nothing about any matter is ever in them. NM's outbound policy admits Gmail for these messages alone, under the owner's
exception (basis `OWNER-2026-11-10-GLOBAL-GMAIL-ACCOUNT-MAIL`); every other route still refuses Gmail.

1. **The sending account.** Use a Gmail address kept for NM (a Google Workspace address on your own domain reads better to
   advocates). Turn on 2-Step Verification for it (Google Account > Security).
2. **An app password.** In that account open Security > 2-Step Verification > App passwords (or go straight to
   `myaccount.google.com/apppasswords`), name it "Nyaymalaw", and create it. Google shows 16 letters in four groups; the spaces are
   not part of it, and NM ignores them. Google offers no app passwords to an account under Advanced Protection or one whose second
   step is a security key only, and a Workspace administrator can turn them off.
3. **The secret file.** Save the app password in a file of its own on the hosting machine, outside the checkout, readable only by
   the account NM runs as (Linux: `chmod 600`; Windows: only that account in the file's security settings). It is read at each send
   and never copied into a log, an error or the project; to change the password, replace the file - no restart is needed.
4. **The settings**, for both processes:

   ```
   NM_MAIL_PROVIDER=gmail
   NM_MAIL_DELIVERY=enabled
   NM_MAIL_SENDER=<the Gmail address>
   NM_GMAIL_APP_PASSWORD_FILE=<the file's absolute path>
   NM_PUBLIC_URL=https://<your domain>
   ```

   NM refuses to start if delivery is enabled without exactly one sign-in file (the app password's, or `NM_GMAIL_TOKEN_FILE`: an
   OAuth access token kept fresh by another tool, which NM does not refresh).
5. **Check it.** After restarting, `GET /api/account-capabilities` says `"mail_delivery": "mailbox"`. Ask for a password reset for
   your own account from the sign-in page and see the mail arrive.
6. **Public sign-up**, if wanted: `NM_PUBLIC_REGISTRATION=enabled`.

NM signs in to `smtp.gmail.com` on port 465 over TLS 1.2 or later, with the server's certificate checked. A send Gmail does not accept
(a refused sign-in, an unreachable server, a refused address) is logged as not delivered, naming neither the address nor the link,
and is never retried by itself; the advocate can ask again, and an admin sending a reset link is told it was not delivered. Revoking
the app password in the Google account stops NM's email at once. Gmail limits how much one account sends - about 500 messages a day
from a personal Gmail account and about 2,000 from a Workspace account, counted over a rolling day, by Google's figures, which
Google may change - ample for confirmations and resets, but a reason to move to a mail service as NM grows.

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

- **Stop, then copy** (plan AN.50, D191). Stop the step worker, then the web server, and only then copy the whole `NM_MATTER_STORE`
  folder; start them again after the copy. A copy of a folder in use is not a backup: a save can land between two files of it, and
  the small databases in it (accounts' usage, the steps) copied in the middle of a write come out stale or damaged. Where the
  machine's disk can be snapshotted as a whole at one instant, stop the processes first all the same.
- Back up the whole folder: conversations, papers, accounts, usage, the outbox and the step stores. Never back up, or put back,
  some of its folders without the others.
- **Not everything in the folder is sealed** (plan AN.53, D222), so treat a backup, and the disk itself, as holding personal data:
  - *Sealed, each matter under its own key:* conversations, papers as sent, the text read from them, and the history's lines.
  - *Sealed under the installation secret alone:* an advocate's settings inside their account record, pending accounts, reset
    links, the mail outbox, and the words of the steps handed to the worker.
  - *Plain text:* the account records themselves, whose file names are the advocates' email addresses (passwords are kept only as
    salted hashes); the sign-in files, each with the record of its owner beside it (a hash,
    no address), and the two sign-in logs; each turn's counts and timings; ratings of replies; the record of
    each matter's last saved version and the record of its owner (`matter-owners/`, a hash of the account's identifier, no
    address); and the identifying columns of the small databases (whose step, whose usage).
  Encrypt the disk and the backups for this reason, and give the folder to the account NM runs as and to no other.
- Keep `NM_MATTER_KEY` (or the file `NM_MATTER_KEY_FILE` names, or `.nm/matter.key`) **apart from** the backups and as safely: a backup without its key cannot be read, and the
  key with a backup opens everything.
- Back up the outgoing-data log too (`egress-*` in `NM_EGRESS_LOG_DIR`, or in `.nm/` under the checkout where that is unset) where its year must outlast the machine.
- Keep the Gmail app password's file out of the backups of the code; if it is backed up, as safely as the key.
- Test a restore on another machine before relying on it.

### Restoring

1. Stop the step worker and the web server.
2. Move the damaged folder aside (do not delete it yet) and put the **whole** backed-up folder in its place, with the key it was
   sealed under.
3. Start the web server and the worker.

A restore puts everything back as it was at the backup, and that is all of it: conversations saved after the backup are gone; an
account made after it does not exist; and a password changed, a sign-in ended, an account suspended or an allowance changed after
the backup is as it was before the change - make those changes again. Usage counted after the backup is forgotten.

**An older copy of one conversation is refused.** Each save records, in `saved-versions/` in the store, which version of the
conversation it saved. A conversation file older than its record - put there by restoring some files and not others, or by a
copying tool - is not opened and not saved over; the advocate's history lists it as a conversation that could not be read, and the
others open as usual. Putting the folder back whole brings its records with it, so a whole restore opens. Where one older file is
deliberately the one meant, stop the processes and delete that conversation's file in `saved-versions/`; it then opens as it is,
and its next save records it. This notices accidents; it is not a seal against someone who can change the folder.

The drill is a test, run offline on a temporary store with invented conversations:
`tests/test_a_restored_store_opens_as_the_backup_left_it.py` copies a stopped store, goes on working, loses the folder, puts the
copy back whole and opens everything; and puts back only some files, which are refused.

## Changing the secret

`python operations/rekey_matter_store.py` replaces `NM_MATTER_KEY` with a new secret (plan AN.50, D190). Run
`python operations/rekey_matter_store.py --dry-run` first: it changes nothing and says what it would do, or why it refuses.

- **Stop the step worker and the web server first.** The command refuses while either is alive on the store, and neither starts
  while it runs.
- It needs the store folder to hold only NM's own files. A file it can neither open with the present secret nor recognise as
  deliberately unsealed refuses the run, as does a link to elsewhere: nothing is skipped. This is one more reason to give
  `NM_MATTER_STORE` a folder of its own.
- It copies the whole store into `rekey-backup-<time>` inside the store and writes the new secret to `new-matter.key` in the store
  (or to `--new-key-file`) **before** it changes anything. It never overwrites a key file that is already there.
- Each re-keyed file is written beside the old one, checked to open with the new secret to exactly what the old one held, swapped
  in and checked again. A failure or an interruption puts back exactly what had been swapped, and says which files it put back and
  which it could not. Exit 0: done. Exit 1: refused, or failed with everything put back - the old secret still opens everything.
  Exit 3: a put-back did not finish - keep both secrets and run it again with `--restore`.
- When it has finished: set `NM_MATTER_KEY` to the contents of the new key file for both processes, move that file out of the store
  to where the key is kept, start the processes, and check that conversations open. Only then delete `rekey-backup-<time>`: it is
  the whole store under the **old** secret, and the command leaves it for the operator to remove.
- A run the machine itself stopped part-way leaves `rekey-in-progress.json` in the store; the next run refuses until
  `python operations/rekey_matter_store.py --restore` has put back what that run listed.

## Restarts and updates

- **Restarting the web server** stops no step: the worker goes on, and the pages pick up again when the server is back.
- **Restarting the worker** stops the steps at work. At its start it takes each one up again by itself, from the work already saved,
  as long as the advocate's sign-in still holds; a message that had not yet begun was never kept and is said as before ("NM was
  restarted before your message reached it"), and the page's own draft lets the advocate send it again.
- **To update NM**: stop the worker (it is safe at any time), stop the web server, update the code, start the worker, start the web
  server. Steps that were at work are taken up again by the worker.

## Logs

- **The outgoing-data log** (owner decision D169) is in the folder `NM_EGRESS_LOG_DIR` names, or in `.nm/` under the checkout
  where that is unset - never in `NM_MATTER_STORE`: one file a day,
  `egress-YYYY-MM-DD.log` by UTC date, one content-free line for every reach to a destination - which kind, which processor, which
  kinds of data and how many bytes; never content, an address or a secret. Both processes write to the same day's file, each line
  whole.
- **It keeps itself**: each process sweeps it as it starts and a minute after each UTC midnight. A day over 90 days old is compressed
  (`.log.gz`, read back before the plain file is deleted); a day over a year old is deleted - the year the Digital Personal Data
  Protection Rules 2025 ask logs of personal-data processing to be kept. `NM_EGRESS_LOG_KEEP_DAYS` sets another period; nothing
  under 180 days, the CERT-In directions' period, is taken. Do not rotate or compress these files with another tool.
- **The single `egress.log` of earlier versions** is taken in at the first start, whole, as the file of the last day it holds, and
  goes a year after that day.
- Each process writes its warnings to its own console; let the supervisor keep them.

## Checked before handing over

- `python -m nm.app.main --check` measures readiness, prints it and exits (plan AN.52, D207). It tries each capability with a real
  act - the store's folder takes a write and a saved conversation opens under the secret; each collection of the held law opens,
  answers one query and reranks one pair (this loads the search models, so it takes as long as the first search does); the
  malware scanner clears harmless bytes - and says `ready`, `not ready` or `not checked` for each. **It must exit 0.** Each
  capability that is not ready is named on a line beginning `NOT READY:` with why, and the command exits 1. `NOT CHECKED:` lines
  (account mail and the AI service have no free check yet) do not fail it. A line beginning `KEPT UNDER THE CODE:` names which of
  the store, the key and the outgoing-data log still have no path of their own. Run it with the same settings the server runs
  with. It starts no server.
- `GET /api/health` answers anyone with one word (plan AN.52, D207): `{"status": "up"}`, or `{"status": "down"}` with HTTP 503. It is
  down where the last readiness measurement found a capability not ready, or where the steps are the step worker's and the worker
  has not been heard from - so an outside monitor that reads it can say when the worker stops. It names no provider, model or
  code fingerprint, and does not say which thing is wrong: `--check` does, and the Admin diagnostics.
- A signed-in advocate's page reads `GET /api/health/detail`: `"steps": {"mode": "separate", "worker": "alive", ...}` with both
  processes running, `"mode": "inside"` with one; how many steps wait and how many are at work - counts only, never whose or what;
  whether the library can be read; and each capability's state.
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
