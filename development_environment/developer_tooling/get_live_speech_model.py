r"""Download the live dictation model into `.nm/models`. F-C-03.

The live words come from a small Indian-English Kaldi model (Vosk, Apache-2.0)
that runs on this machine's processor; the text the advocate KEEPS is still
transcribed by Whisper large-v3. This script fetches only the live model.

    python development_environment/developer_tooling/get_live_speech_model.py
    python development_environment/developer_tooling/get_live_speech_model.py --check

WHY THIS IS A SCRIPT AND NOT A README LINE
--------------------------------------------
`NM_DICTATION_LIVE_MODEL` and the `.nm/models` location are decided in
`nm.bootstrap.composition`. A hand-typed download that unzips somewhere else
leaves `readiness()` reporting NO MODEL with the model sitting on disk -- a
document's claim about an artefact, disagreeing with the filesystem. So the
destination is read from the same default the product reads.

SSLKEYLOGFILE IS CLEARED FIRST, and that is not incidental: Norton injects
`SSLKEYLOGFILE=\\.\nllMonFltProxy\<hex>` into the inherited environment, CPython
hands it to OpenSSL as a keylog path, and the process ABORTS on the first TLS
call of any kind -- `OPENSSL_Uplink(...): no OPENSSL_Applink`. It is present in
some shells and absent in others, which is why it reads as intermittent.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

# Before `ssl` is reached by anything: see the module docstring.
os.environ.pop("SSLKEYLOGFILE", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_MODEL = "vosk-model-small-en-in-0.4"
SOURCE = "https://alphacephei.com/vosk/models/{name}.zip"


def destination() -> Path:
    """Where the product looks, not where this script would like it to be."""
    name = os.environ.get("NM_DICTATION_LIVE_MODEL") or DEFAULT_MODEL
    return ROOT / ".nm" / "models" / name


def readiness() -> str:
    from nm.adapters.speech.vosk_live import VoskLive

    return VoskLive(model_dir=destination()).readiness()


def fetch(into: Path) -> None:
    import urllib.request

    url = SOURCE.format(name=into.name)
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as response:  # noqa: S310 -- fixed https host
        payload = response.read()
    print(f"  {len(payload) / 1_048_576:.1f} MB, unzipping into {into.parent}")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        top = {Path(n).parts[0] for n in archive.namelist()}
        if top != {into.name}:
            raise SystemExit(
                f"the archive unpacks to {sorted(top)}, not {into.name!r}; refusing to "
                f"scatter it across .nm/models")
        into.parent.mkdir(parents=True, exist_ok=True)
        archive.extractall(into.parent)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report readiness and download nothing")
    args = parser.parse_args()

    into = destination()
    if args.check:
        print(f"{into}\n  {readiness()}")
        return 0
    if (into / "am").is_dir():
        print(f"already on disk: {into}\n  {readiness()}")
        return 0
    fetch(into)
    if not (into / "am").is_dir():
        raise SystemExit(f"unzipped, but {into / 'am'} is not there -- the model is not usable")
    print(f"  {readiness()}")
    print("Restart the server for /api/health to load it on first use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
