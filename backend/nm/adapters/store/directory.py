"""A1 — the file-backed directory. Sealed with the same key as the matters.

WHY THE SAME CIPHER AND NOT A SECOND ONE
------------------------------------------
CLAUDE.md §4 asks what refuses the second copy. Two encryption paths in one
product means one of them gets hardened and the other does not, and the one
that does not is discovered by an incident. `_Cipher` is imported from the
matter store rather than reimplemented, so there is exactly one answer to
"how is data at rest sealed here".

WHAT IS ON DISK AND WHAT IS NOT
---------------------------------
Advocates and their derived credentials; sessions by token FINGERPRINT. The
password is never written, the token is never written, and a stolen store is
therefore not a set of live logins.

FAILURES ARE RECORDED HERE, NOT RETURNED
------------------------------------------
`authenticate` returns `None` for an unknown advocate and for a wrong
password, and writes WHICH to the audit line. The distinction is exactly what
the caller must not learn and exactly what an operator needs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from dataclasses import replace
from datetime import datetime
from io import BufferedRandom
from pathlib import Path

from nm.adapters.store.file_store import _Cipher
from nm.domain import attempts
from nm.domain.advocate import (
    AccountSecurity,
    AdvocateIdentity,
    Consent,
    Credential,
    Enrolment,
    Invitation,
    PasswordReset,
    PasswordResetResult,
    Session,
    advocate_id_is_storage_safe,
    canonical_id,
    dummy,
    new_invitation,
    new_password_reset,
    open_session,
    registration_email,
    token_fingerprint,
)
from nm.domain.names import discard
from nm.domain.professional_access import ProfessionalApproval
from nm.domain.traceability import implements
from nm.ports.directory import (  # noqa: F401
    AccountBusy,
    AlreadyEnrolled,
    AuthenticationUnavailable,
    InvitationRefused,
    RegistrationUnavailable,
    SessionsUnavailable,
)

# A public door must not grow an unbounded history even with many sources.
# At capacity, refuse until existing records expire; never evict live limits.
REGISTRATION_MAX_RECORDS = 10_000
REGISTRATION_MAX_BYTES = 2 * 1024 * 1024

#: ONE REFUSAL, ONE SENTENCE, AND DELIBERATELY NO ORACLE. BK-31.
#:
#: Unknown, expired, replayed and identity-mismatched all say exactly this.
#: Distinguishing them would turn an invitation token into a probe for who is
#: on the roster and which workspace they belong to -- the caller learns
#: nothing; `_note` records the precise cause where the operator can read it.
#:
#: IT ALSO SAYS WHAT TO DO NEXT, which is a rule this row already had: an
#: advocate who cannot enrol and is told nothing simply leaves, and a
#: controlled roster then reads as a broken product.
#:
#: HELD ONCE because it was written three times, and a message repeated at
#: three raise sites drifts at two of them -- CLAUDE.md §4.
_INVITATION_REFUSED = (
    "That invitation was not recognised or is no longer active. Nothing was "
    "saved. Ask whoever administers this installation to send you a new one.")

#: Fields an account record held while recovery codes existed. Implementation Plan
#: F-A-04 removed recovery codes from the product; a record that still carries any of these
#: has them dropped at its next successful sign-in or password reset.
RETIRED_RECOVERY_FIELDS = ("recovery_codes", "recovery_codes_issued_at",
                           "recovery_generation")


class _AccountClaim:
    """A non-blocking OS lock; closing it also releases it after a crash."""

    def __init__(self, handle: BufferedRandom) -> None:
        self._handle = handle

    def release(self) -> None:
        if self._handle.closed:
            return
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()


@implements("A1")
class FileDirectory:
    def begin_pending_registration(self, enrolment: Enrolment, now: datetime) -> dict:
        from nm.adapters.store.pending_accounts import PendingAccounts
        return PendingAccounts(self).begin(enrolment, now)

    def resend_registration(self, email: str, now: datetime) -> str | None:
        from nm.adapters.store.pending_accounts import PendingAccounts
        return PendingAccounts(self).resend(email, now)

    def cancel_pending_registration(self, email: str, flow: str, now: datetime) -> bool:
        from nm.adapters.store.pending_accounts import PendingAccounts
        return PendingAccounts(self).cancel(email, flow, now)

    def confirm_registration(self, email: str, code: str, flow: str,
                             credential: Credential | None, now: datetime) -> AdvocateIdentity:
        from nm.adapters.store.pending_accounts import PendingAccounts
        return PendingAccounts(self).confirm(email, code, flow, credential, now)

    def device_draft_key(self, advocate_id: str, device: str) -> dict:
        """One stable, protected key per account/device; no client material here."""
        from cryptography.fernet import InvalidToken

        if self.identity(advocate_id) is None or not device:
            raise ValueError("a current account and device are required")
        if self._cipher.scheme != "fernet":
            raise ValueError("authenticated draft protection is unavailable")
        namespace = hashlib.sha256(
            json.dumps([canonical_id(advocate_id), device]).encode("utf8")).hexdigest()
        folder = self._root / "draft-keys"
        folder.mkdir(exist_ok=True)
        path = folder / f"{namespace}.nm"
        claim = self._claim_account(advocate_id)
        if claim is None:
            raise AccountBusy("account access is already changing")
        try:
            if not path.exists():
                # The key is never stored beside browser ciphertext. An expired
                # session cannot retrieve it, even when that ciphertext remains.
                sealed = self._cipher.encrypt(secrets.token_bytes(32))
                with path.open("xb") as handle:
                    handle.write(sealed)
                    handle.flush()
                    os.fsync(handle.fileno())
            try:
                key = self._cipher.decrypt(path.read_bytes())
            except InvalidToken as exc:
                raise ValueError("draft protection is unreadable") from exc
            if len(key) != 32:
                raise ValueError("draft protection is unavailable")
            return {"namespace": namespace,
                    "key": base64.b64encode(key).decode("ascii"),
                    "lifetime_hours": 72}
        finally:
            claim.release()

    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._advocates = self._root / "advocates"
        self._advocates_by_digest = self._advocates / "by-digest"
        self._sessions = self._root / "sessions"
        self._audit = self._root / "auth.log"
        self._attempts = self._root / "attempts.log"
        self._registration_attempts = self._root / "registration-attempts.json"
        self._registration_lock = self._root / "registration-attempts.lock"
        self._invitations = self._root / "invitations"
        self._used_invitations = self._invitations / "used"
        self._account_locks = self._root / "account-locks"
        self._resets = self._root / "password-resets"
        self._advocates.mkdir(parents=True, exist_ok=True)
        self._advocates_by_digest.mkdir(parents=True, exist_ok=True)
        self._sessions.mkdir(parents=True, exist_ok=True)
        self._resets.mkdir(parents=True, exist_ok=True)
        self._invitations.mkdir(parents=True, exist_ok=True)
        self._used_invitations.mkdir(parents=True, exist_ok=True)
        self._account_locks.mkdir(parents=True, exist_ok=True)
        self._auth_state = threading.local()
        self._cipher = _Cipher(
            key if key is not None else os.environ.get("NM_MATTER_KEY", ""))

    # ---------------------------------------------------------- invitations ---

    def _invitation_path(self, fingerprint: str) -> Path:
        return self._invitations / f"{fingerprint}.nm"

    def issue_invitation(self, identity: AdvocateIdentity, issued_by: str,
                         now: datetime) -> str:
        token, invitation = new_invitation(identity, issued_by, now)
        record = {
            "token_fingerprint": invitation.token_fingerprint,
            "identity": invitation.identity.as_dict(),
            "issued_at": invitation.issued_at.isoformat(),
            "expires_at": invitation.expires_at.isoformat(),
            "issued_by": invitation.issued_by,
        }
        # Exclusive creation: a fantastically unlikely token collision is a
        # refusal, never an overwrite of somebody else's invitation.
        payload = json.dumps(record, indent=2).encode("utf8")
        with self._invitation_path(invitation.token_fingerprint).open(
                "xb") as handle:
            # Invitation identity is roster data. It receives the same seal as
            # advocate records; only the random token's fingerprint is visible
            # in the filename.
            handle.write(self._cipher.encrypt(payload))
        self._note(identity.id, f"invitation issued by {invitation.issued_by}")
        return token

    def accept_invitation(self, token: str, credential: Credential,
                          now: datetime, consent: Consent | None = None,
                          ) -> AdvocateIdentity:
        """Claim on disk and enrol; every other instance sees the claim."""
        fingerprint = token_fingerprint((token or "").strip())
        active = self._invitation_path(fingerprint)
        used = self._used_invitations / f"{fingerprint}.nm"
        audit_key = f"invitation:{fingerprint}"
        try:
            sealed = active.read_bytes()
            data = json.loads(self._cipher.decrypt(sealed).decode("utf8"))
            invitation = Invitation(
                token_fingerprint=data["token_fingerprint"],
                identity=AdvocateIdentity(**data["identity"]),
                issued_at=datetime.fromisoformat(data["issued_at"]),
                expires_at=datetime.fromisoformat(data["expires_at"]),
                issued_by=data["issued_by"],
            )
        except Exception:  # noqa: BLE001 -- corrupt/foreign is still refused
            self._note(audit_key, "invitation refused: unknown or already used")
            raise InvitationRefused(_INVITATION_REFUSED) from None

        active_now = invitation.active_at(now)
        if not active_now:
            self._note(invitation.identity.id, "invitation refused: expired")
            raise InvitationRefused(_INVITATION_REFUSED)

        # `threading.Lock` protects one Python object. Registration can be
        # served by many directory objects and, in production, many worker
        # processes. Exclusive creation of the used record is the shared
        # compare-and-set: exactly one claimant can create this path. Copy the
        # sealed record before removing the active name so an unexpected I/O
        # failure can restore the invitation without exposing roster data.
        try:
            with used.open("xb") as claim:
                claim.write(sealed)
        except FileExistsError:
            self._note(audit_key, "invitation refused: concurrent replay")
            raise InvitationRefused(_INVITATION_REFUSED) from None
        except OSError:
            self._note(audit_key, "invitation refused: claim unavailable")
            raise InvitationRefused(_INVITATION_REFUSED) from None

        # THE CLAIM IS HELD FROM HERE, AND NOTHING BELOW MAY SURRENDER IT.
        #
        # Removing the active name is HYGIENE, not the claim. `used` is the
        # sole authority on whether this fingerprint is spent -- nothing else
        # in the product reads the active directory -- so a presentation that
        # still finds the active record is refused by the exclusive create
        # above regardless of whether this succeeded.
        #
        # It used to raise AND delete `used`, which un-spent a claim the other
        # claimant had ALREADY been refused against: both callers were refused
        # and the invitation went back on the door. On Windows that is not
        # hypothetical -- removing a file another thread still holds open
        # raises -- and `test_two_directory_instances_cannot_both_spend_one_
        # invitation` caught it on the first of twenty attempts.
        if not discard(active):
            self._note(audit_key, "invitation claimed; active record retained")

        try:
            # The FILE, not the request, owns the identity that is saved.
            self.enrol(Enrolment(identity=invitation.identity,
                                 credential=credential, created_at=now,
                                 consent=consent))
        except AlreadyEnrolled:
            self._note(invitation.identity.id,
                       "invitation consumed: advocate already enrolled")
            raise
        except Exception:
            # An I/O failure is not consumption. NOTHING WAS DELIVERED here, so
            # the claim is RELEASED rather than held, and exactly one live
            # record is left behind -- whichever name survived the hygiene step
            # above -- so the operator does not have to reissue after a
            # transient disk error.
            if active.exists():
                discard(used)
            else:
                try:
                    os.replace(used, active)
                except OSError:
                    self._note(audit_key,
                               "enrolment failed and the invitation could not "
                               "be restored; it must be reissued")
            raise
        self._note(invitation.identity.id, "invitation consumed and enrolled")
        return invitation.identity

    # ------------------------------------------------------------ advocates ---

    def _advocate_path(self, advocate_id: str) -> Path:
        """FOLDED HERE, once, for every door.

        `enrol`, `identity`, `authenticate` and the failed-attempt note all
        reach the store through this, so a capital an advocate types at
        sign-in is not a different advocate -- and cannot be, rather than
        being one that four call sites each remember not to make.

        `AdvocateIdentity` refuses a non-canonical id, so nothing can be
        enrolled under a second spelling either. Two mechanisms, one rule:
        the type refuses bad data going in, this folds queries coming from
        outside, and neither is sufficient alone.
        """
        canonical = canonical_id(advocate_id)
        if not advocate_id_is_storage_safe(canonical):
            # Public lookup input must fail closed, not turn into a 500, while
            # no untrusted value is ever allowed to become a path component.
            digest = hashlib.sha256(canonical.encode("utf8")).hexdigest()
            return self._advocates / f"invalid-{digest}.nm"
        if len(canonical) + len(".nm") > 255:
            # Valid email can be 254 characters, beyond one filename with its
            # extension. A disjoint namespace cannot collide with an ordinary
            # caller-selected ID; old usable account paths do not move.
            digest = hashlib.sha256(canonical.encode("utf8")).hexdigest()
            return self._advocates_by_digest / f"{digest}.nm"
        return self._advocates / f"{canonical}.nm"

    @staticmethod
    def _credential_record(credential: Credential) -> dict:
        return {
            "algorithm": credential.algorithm,
            "salt": credential.salt,
            "hash": credential.hash,
            "n": credential.n,
            "r": credential.r,
            "p": credential.p,
        }

    def _write_account(self, path: Path, blob: dict,
                       security: AccountSecurity) -> None:
        """THE ONLY PLACE THE GENERATION COUNTER IS PERSISTED. F-A-03.

        Every write that touches account security material comes through here
        and must SAY what happened to the credential generation -- moved, for a
        password change; unchanged, for removing retired recovery material. A
        rule keyed on the write instead would call every record rewrite a
        password change and retire every outstanding reset link for nothing.

        Making the caller pass the transition puts that judgement at the site,
        where it is reviewable, instead of inside a heuristic.
        """
        blob.update(security.as_dict())
        # RETIRED MATERIAL NEVER SURVIVES A WRITE. Every account write passes
        # here, so no writer has to remember to drop recovery-code digests or
        # their counter -- which is how one of them would eventually forget.
        for name in RETIRED_RECOVERY_FIELDS:
            blob.pop(name, None)
        self._replace_advocate(path, blob)

    def _replace_advocate(self, path: Path, blob: dict) -> None:
        """Replace an account-control record without exposing a partial JSON write."""
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("x", encoding="utf8") as handle:
                handle.write(json.dumps(blob, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            # The replace either happened or it did not; the temporary name
            # decides nothing either way, so its removal may not raise over a
            # write that succeeded.
            discard(temporary)

    def enrol(self, enrolment: Enrolment) -> None:
        path = self._advocate_path(enrolment.identity.id)
        blob = {
            "identity": enrolment.identity.as_dict(),
            "credential": self._credential_record(enrolment.credential),
            "created_at": enrolment.created_at.isoformat(),
            # A NEW ACCOUNT IS GENERATION 1, not 0. Zero is what an account
            # enrolled before this model existed reads as, and the two must be
            # distinguishable: a reset link issued against a legacy account
            # records 0, and the account's first credential change moving it
            # to 1 is exactly the change that link must be refused for.
            **AccountSecurity(credential_generation=1).as_dict(),
        }
        # WITH THE ACCOUNT IT PERMITS, written in the same exclusive create, so
        # there is no instant at which the account exists and its consent does
        # not. Implementation Plan F-A-09; DPDP Act 2023 s.6(10).
        if enrolment.consent is not None:
            blob["consent"] = enrolment.consent.as_dict()
        if enrolment.mailbox_confirmed_at is not None:
            blob['mailbox_confirmed_at'] = enrolment.mailbox_confirmed_at.isoformat()
        if enrolment.activation_id is not None:
            blob['activation_id'] = enrolment.activation_id
        # IN THE OPEN, DELIBERATELY (BK-22). The credential is an scrypt
        # hash with its salt and cost -- scrypt exists so that such a hash
        # can be stored where it can be read. Sealing it AS WELL made
        # signing in depend on `NM_MATTER_KEY`, a key that is meant to
        # rotate, and rotating it locked every advocate out.
        #
        # Client material is not here and is not affected: matters,
        # transcripts and metrics keep the matter key.
        temporary = path.with_name(f'.{path.name}.{secrets.token_hex(8)}.tmp')
        try:
            # Publish a complete, flushed record exclusively. Opening the
            # final path for writing exposed partial accounts after a crash.
            with temporary.open('x', encoding='utf8') as handle:
                handle.write(json.dumps(blob, indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
        except FileExistsError as exc:
            raise AlreadyEnrolled(
                f"{enrolment.identity.id} is already enrolled. Overwriting "
                f"would replace a credential without anyone deciding to.") from exc
        finally:
            discard(temporary)

    # ----------------------------------------------- public signup admission ---

    def admit_registration(self, email: str, source: str,
                           now: datetime) -> attempts.Verdict:
        """One locked rolling ledger for all workers, including successes.

        Persist admission before credential derivation/account creation. A
        crash may consume an attempt, but can never create an uncounted account.
        This is independent of the historical failed-authentication log, whose
        controlled-local availability policy is intentionally not suitable for
        a public account-creation door.
        """
        if registration_email(email) != email or not source:
            raise ValueError("registration admission needs a canonical email and source")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("registration admission needs an aware clock")
        try:
            claim = self._claim_path(self._registration_lock)
        except OSError as exc:
            raise RegistrationUnavailable("registration admission unavailable") from exc
        if claim is None:
            raise RegistrationUnavailable("registration admission busy")
        try:
            records = []
            try:
                with self._registration_attempts.open("rb") as handle:
                    raw = handle.read(REGISTRATION_MAX_BYTES + 1)
            except FileNotFoundError:
                raw = None
            if raw is not None:
                if len(raw) > REGISTRATION_MAX_BYTES:
                    raise ValueError("registration admission exceeds its storage bound")
                doc = json.loads(raw)
                if (not isinstance(doc, dict) or set(doc) != {"schema", "attempts"}
                        or type(doc["schema"]) is not int or doc["schema"] != 1
                        or not isinstance(doc["attempts"], list)
                        or len(doc["attempts"]) > REGISTRATION_MAX_RECORDS):
                    raise ValueError("invalid registration admission envelope")
                for row in doc["attempts"]:
                    if (not isinstance(row, dict) or set(row) != {"at", "email", "source"}
                            or not isinstance(row["at"], str)
                            or any(not isinstance(row[key], str)
                                   or len(row[key]) != 64
                                   or any(c not in "0123456789abcdef" for c in row[key])
                                   for key in ("email", "source"))):
                        raise ValueError("invalid registration admission record")
                    at = datetime.fromisoformat(row["at"])
                    if at.tzinfo is None or at.utcoffset() is None or at > now:
                        raise ValueError("registration admission clock is not established")
                    if now - at < attempts.WINDOW:
                        records.append((row, at))
            email_key = hashlib.sha256(email.encode("utf8")).hexdigest()
            source_key = hashlib.sha256(source.encode("utf8")).hexdigest()
            decision = attempts.verdict(
                tuple(at for row, at in records if row["email"] == email_key),
                tuple(at for row, at in records if row["source"] == source_key), now)
            if not decision.allowed:
                return decision
            if len(records) >= REGISTRATION_MAX_RECORDS:
                raise ValueError("registration admission population is full")
            rows = [row for row, _ in records]
            rows.append({"at": now.isoformat(), "email": email_key, "source": source_key})
            doc = {"schema": 1, "attempts": rows}
            if len(json.dumps(doc, indent=2).encode("utf8")) > REGISTRATION_MAX_BYTES:
                raise ValueError("registration admission storage is full")
            self._replace_advocate(self._registration_attempts, doc)
            return decision
        except (OSError, ValueError, TypeError) as exc:
            raise RegistrationUnavailable("registration admission unavailable") from exc
        finally:
            claim.release()

    # ------------------------------------------------------- account claims ---

    def _account_lock_path(self, advocate_id: str) -> Path:
        digest = hashlib.sha256(canonical_id(advocate_id).encode("utf8")).hexdigest()
        return self._account_locks / f"{digest}.lock"

    def _claim_account(self, advocate_id: str) -> _AccountClaim | None:
        """Own account access across workers; the OS retires crashed claims.

        Held by sign-in, by a password reset and by an approval write, so a
        session can never be minted against a credential that is being replaced.
        """
        return self._claim_path(self._account_lock_path(advocate_id))

    @staticmethod
    def _claim_path(path: Path) -> _AccountClaim | None:
        """Shared nonblocking process claim for an explicitly owned record."""
        handle = path.open("a+b")
        try:
            if path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return _AccountClaim(handle)
        except (OSError, BlockingIOError):
            handle.close()
            return None

    def authenticate_and_open_session(
            self, advocate_id: str, password: str, device: str, now: datetime,
            *, client_label: str = '', source: str = '',
            ) -> tuple[AdvocateIdentity, str] | None:
        """Keep successful authentication and session issue on one generation."""
        if not self._advocate_path(advocate_id).exists():
            # Unknown public input still pays the normal dummy derivation and
            # audit path, but must not create an unbounded population of
            # persistent lock artifacts.
            self.authenticate(advocate_id, password)
            return None
        claim = self._claim_account(advocate_id)
        if claim is None:
            raise AccountBusy("account access is already changing")
        try:
            identity = self.authenticate(advocate_id, password)
            if identity is None:
                return None
            doc = self._read(identity.id)
            if doc is None:
                return None
            if any(name in doc for name in RETIRED_RECOVERY_FIELDS):
                # RECOVERY CODES NO LONGER EXIST, so their digests do not stay
                # on disk waiting for a route that is gone. `_write_account`
                # drops them; nothing about the credential moved, and the
                # transition passed says so.
                try:
                    self._write_account(self._advocate_path(identity.id), doc,
                                        AccountSecurity.read(doc))
                    self._note(identity.id, "retired recovery-code material removed")
                except OSError:
                    # The account still authenticated. Refusing the sign-in over
                    # housekeeping would lock out an advocate for nothing; the
                    # removal is retried at the next sign-in.
                    self._note(identity.id,
                               "retired recovery-code material could not be removed")
            token = self.open_session(identity.id, device, now,
                                      client_label=client_label, source=source)
            return identity, token
        finally:
            claim.release()

    # ------------------------------------------------------- password reset ---
    #
    # A forgotten password is replaced through a link sent to the account's
    # email address; there are no recovery codes (Implementation Plan, phase A).
    # The link's token is never stored -- only its fingerprint, sealed -- and a
    # stolen store is therefore not a set of working reset links.

    def _reset_path(self, fingerprint: str) -> Path:
        return self._resets / f"{fingerprint}.nm"

    def _write_reset(self, reset: PasswordReset, *, exclusive: bool) -> None:
        """Sealed, like every record that names an advocate. Never the token."""
        sealed = self._cipher.encrypt(
            json.dumps(reset.as_dict(), indent=2).encode("utf8"))
        path = self._reset_path(reset.token_fingerprint)
        if exclusive:
            # A fantastically unlikely fingerprint collision is a refusal,
            # never an overwrite of somebody else's link.
            with path.open("xb") as handle:
                handle.write(sealed)
            return
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(sealed)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            discard(temporary)

    def _read_reset(self, fingerprint: str) -> PasswordReset | None:
        path = self._reset_path(fingerprint)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            return PasswordReset.from_dict(
                json.loads(self._cipher.decrypt(raw).decode("utf8")))
        except Exception:  # noqa: BLE001 -- an unreadable link is not a link
            self._note("password-reset", "reset record unreadable")
            return None

    def _discard_finished_resets(self, now: datetime) -> None:
        """Hygiene: a link past its expiry can never be used, so its record goes."""
        for path in self._resets.glob("*.nm"):
            reset = self._read_reset(path.stem)
            if reset is not None and now >= reset.expires_at:
                discard(path)

    def issue_password_reset(self, email: str, now: datetime) -> str | None:
        """A reset token ONCE, or `None` -- and the caller must not say which."""
        canonical = canonical_id(email)
        doc = self._read(canonical)
        if doc is None:
            self._note(canonical, "password reset requested: no readable account")
            return None
        identity = AdvocateIdentity(**doc["identity"])
        try:
            deliverable = bool(identity.email) and (
                registration_email(identity.email) == identity.email)
        except ValueError:
            deliverable = False
        if not deliverable:
            # An operator-enrolled id with no email has nowhere to send a link.
            self._note(identity.id,
                       "password reset requested: account has no email to send to")
            return None
        self._discard_finished_resets(now)
        token, reset = new_password_reset(identity.id, AccountSecurity.read(doc), now)
        self._write_reset(reset, exclusive=True)
        self._note(identity.id, f"password reset link issued, expires "
                                f"{reset.expires_at.isoformat()}")
        return token

    def reset_password(self, token: str, credential: Credential,
                       now: datetime) -> PasswordResetResult:
        """Spend one link, replace the credential and end every session."""
        fingerprint = token_fingerprint((token or "").strip())
        reset = self._read_reset(fingerprint)
        if reset is None:
            self._note("password-reset", "password reset refused: unknown link")
            return PasswordResetResult(False)
        canonical = reset.advocate_id
        claim = self._claim_account(canonical)
        if claim is None:
            raise AccountBusy("account access is already changing")
        try:
            # Re-read both under the claim: another worker may have spent this
            # link, or changed the password, since the optimistic read above.
            doc = self._read(canonical)
            reset = self._read_reset(fingerprint)
            if doc is None or reset is None:
                why = "the account or the link could not be read"
            else:
                why = reset.why_not(security=AccountSecurity.read(doc), now=now)
            if why is not None:
                self._note(canonical, f"password reset refused: {why}")
                return PasswordResetResult(False)

            # SPENT BEFORE THE DOOR CHANGES, and the order is the decision. A
            # failure after this leaves a used link and an unchanged password --
            # the advocate asks for another link. The other order could leave a
            # live link beside a changed password: a second reset for free.
            self._write_reset(replace(reset, consumed_at=now), exclusive=False)
            # End old grants before changing the credential. A reset is what an
            # advocate reaches for when a device or password is compromised, so
            # no earlier session survives it.
            ended = self.close_all_sessions(canonical, "password reset")
            doc["credential"] = self._credential_record(credential)
            doc["credential_changed_at"] = now.isoformat()
            self._write_account(self._advocate_path(canonical), doc,
                                AccountSecurity.read(doc).with_new_credential())
            self._note(canonical, f"password reset by emailed link; "
                                  f"{ended} sessions ended")
            return PasswordResetResult(True, ended)
        finally:
            claim.release()

    #: Why a sign-in failed, in the caller's vocabulary. THREE STATES.
    #:
    # `unreadable` is the one that is neither a wrong email nor a wrong
    # password: a record encrypted under a key the server no longer has.
    # It happened on 7 September 2026 -- an account enrolled under one
    # `NM_MATTER_KEY` and read under another -- and the advocate was told
    # their credentials were wrong. No amount of retyping fixes that.
    UNKNOWN = "unknown"
    WRONG_PASSWORD = "wrong_password"
    UNREADABLE = "unreadable"

    def _read(self, advocate_id: str) -> dict | None:
        self._auth_state.last_failure = self.UNKNOWN
        canonical = canonical_id(advocate_id)
        if not advocate_id_is_storage_safe(canonical):
            return None
        try:
            path = self._advocate_path(canonical)
            if not path.exists():
                return None
            raw = path.read_bytes()
            # PLAIN FIRST, SEALED SECOND. Records written before BK-22 are
            # encrypted, and this reads both -- so no account breaks and
            # there is no window in which sign-in is down. A record is
            # rewritten in the open the next time it is written.
            sealed = False
            try:
                doc = json.loads(raw.decode("utf8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                doc = json.loads(self._cipher.decrypt(raw).decode("utf8"))
                sealed = True
            # The path is an account key, not permission to adopt whichever
            # identity happens to be stored there. Malformed readable JSON is
            # an unreadable account, just like an unusable seal.
            if not isinstance(doc, dict):
                raise ValueError("account record must be an object")
            identity = AdvocateIdentity(**doc["identity"])
            if identity.id != canonical:
                raise ValueError("account identity does not match its storage key")
            Credential(**doc["credential"])
            if sealed:
                # MIGRATED ON THE WAY PAST, and it has to be here.
                #
                # `enrol` is the only other writer and it REFUSES to
                # overwrite, so a record sealed before BK-22 would stay
                # sealed forever and sign-in would keep depending on the
                # matter key -- which is the whole thing being removed.
                # Measured: unsealing the writer alone changed nothing for
                # the one account that already existed.
                #
                # ONLY REACHED WHEN THE DECRYPT SUCCEEDED, so this runs
                # exactly once per record, on a turn where the correct key
                # was present. It never converts something it could not
                # read.
                try:
                    path.write_text(json.dumps(doc, indent=2),
                                    encoding="utf8")
                except OSError:
                    # A record that could not be rewritten still verified.
                    # Failing the sign-in over a migration would be the
                    # cure harming more than the disease.
                    pass
            self._auth_state.last_failure = None
            return doc
        except Exception as exc:  # noqa: BLE001
            # A RECORD THAT WILL NOT OPEN IS NOT AN ABSENT ONE. It was
            # visible only to the operator until the advocate was told
            # their credentials were wrong on a record that existed and
            # was correct.
            self._auth_state.last_failure = self.UNREADABLE
            self._note(advocate_id, f"record unreadable: {type(exc).__name__}")
            return None

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        doc = self._read(advocate_id)
        return AdvocateIdentity(**doc["identity"]) if doc else None

    # ----------------------------------------- professional approval ---
    def _professional_records(self, doc: dict, advocate_id: str) -> list[dict]:
        sealed = doc.get("professional_approval")
        if sealed is None:
            return []
        if not isinstance(sealed, str):
            raise ValueError("professional approval record is unreadable")
        envelope = json.loads(self._cipher.decrypt(sealed.encode("ascii")).decode("utf8"))
        if (not isinstance(envelope, dict) or set(envelope) != {"schema", "records"}
                or type(envelope["schema"]) is not int or envelope["schema"] != 1
                or not isinstance(envelope["records"], list) or not envelope["records"]):
            raise ValueError("professional approval history is unreadable")
        for version, row in enumerate(envelope["records"], 1):
            approval = ProfessionalApproval.from_record(row)
            if (approval is None or approval.account_id != canonical_id(advocate_id)
                    or approval.version != version):
                raise ValueError("professional approval history is inconsistent")
        return envelope["records"]

    def professional_approval(self, advocate_id: str) -> dict | None:
        """Approval failure denies only the privileged operation, never sign-in."""
        try:
            doc = self._read(advocate_id)
            rows = self._professional_records(doc, advocate_id) if isinstance(doc, dict) else []
            return rows[-1] if rows else None
        except Exception:  # noqa: BLE001 — damaged approval cannot grant authority
            return None

    def record_professional_approval(self, approval: ProfessionalApproval, *,
                                     expected_version: int, now: datetime) -> dict:
        """Operator-only CAS; there is deliberately no public HTTP writer.

        Review metadata is sealed independently within the account record. Its
        loss cannot break password authentication or turn absence into approval.
        Existing security fields and every prior approval are retained.
        """
        if (not isinstance(approval, ProfessionalApproval)
                or type(expected_version) is not int or expected_version < 0
                or approval.version != expected_version + 1
                or not isinstance(now, datetime) or now.tzinfo is None
                or now.utcoffset() is None or approval.approved_at > now
                or (approval.revoked_at is not None and approval.revoked_at > now)
                or (approval.revoked_at is None and approval.valid_until <= now)):
            raise ValueError("supply a current attributed approval and the observed version")
        claim = self._claim_account(approval.account_id)
        if claim is None:
            raise AccountBusy("account is being changed; retry from its current approval")
        try:
            doc = self._read(approval.account_id)
            if not isinstance(doc, dict):
                raise ValueError("approval requires an existing readable account")
            rows = self._professional_records(doc, approval.account_id)
            if len(rows) != expected_version:
                raise ValueError("professional approval moved; read its current version")
            if approval.revoked_at is not None:
                prior = ProfessionalApproval.from_record(rows[-1]) if rows else None
                if (prior is None or prior.revoked_at is not None
                        or prior.revoke(approval.revoked_by, approval.revocation_reason,
                                        approval.revoked_at) != approval):
                    raise ValueError("revocation must preserve the approval being revoked")
            elif rows:
                prior = ProfessionalApproval.from_record(rows[-1])
                if prior is None:
                    raise ValueError("professional approval history is unreadable")
                prior_at = prior.revoked_at or prior.approved_at
                if approval.approved_at < prior_at:
                    raise ValueError("a replacement review cannot precede its predecessor")
            envelope = {"schema": 1, "records": [*rows, approval.as_dict()]}
            doc["professional_approval"] = self._cipher.encrypt(
                json.dumps(envelope).encode("utf8")).decode("ascii")
            self._replace_advocate(self._advocate_path(approval.account_id), doc)
            return approval.as_dict()
        finally:
            claim.release()

    # ------------------------------------------------- rate limiting ---
    #
    # BK-20/BK-18. The product had none, and the password validator said
    # so in a message the ADVOCATE reads -- *this is the only thing
    # standing between one advocate's client file and another's, and the
    # product has no rate limit yet*. Naming which of three things failed
    # at sign-in made that gap worth more, so the two landed together.

    def failures_since(self, advocate_id: str, source: str,
                       since: datetime) -> tuple[tuple, tuple] | None:
        """(this address's failures, this source's failures), or None.

        None means the limiter could not run, not that there were no failures.
        New credential attempts must refuse admission until it is restored.
        """
        if not self._attempts.exists():
            return ((), ())
        try:
            raw = self._attempts.read_text(encoding="utf8")
        except (OSError, UnicodeError):
            return None

        wanted = canonical_id(advocate_id)
        mine: list = []
        here: list = []
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                return None
            stamp, who, where = parts
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                return None
            if when.utcoffset() is None:
                return None
            if when < since:
                continue
            if who == wanted:
                mine.append(when)
            if where == source:
                here.append(when)
        return (tuple(mine), tuple(here))

    def note_failure(self, advocate_id: str, source: str,
                     now: datetime) -> None:
        """One durable line per failed attempt; unavailable is an explicit refusal.

        NO CLIENT MATERIAL. A timestamp, a folded id and a source -- the
        same shape the auth log beside it has held since slice 1.
        """
        try:
            with self._attempts.open("a", encoding="utf8") as fh:
                who = _one_log_field(canonical_id(advocate_id))
                where = _one_log_field(source)
                fh.write(f"{now.isoformat()}\t{who}\t{where}\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise AuthenticationUnavailable('Attempt could not be recorded.') from exc

    def limiter_available(self) -> bool:
        """Whether the attempt log can be written. Reported at /api/health
        so a limiter that is not running is visible BEFORE an incident.
        """
        try:
            with self._attempts.open('a', encoding='utf8'):
                pass
            return self.failures_since('', '', datetime.now().astimezone()) is not None
        except OSError:
            return False

    def why_last_sign_in_failed(self) -> str | None:
        """`unknown`, `wrong_password`, `unreadable`, or None.

        Read immediately after `authenticate` returns None. A field rather
        than a second return value because every other caller of
        `authenticate` wants the identity and nothing else, and widening
        the signature would make them all handle a reason they discard.
        """
        return getattr(self._auth_state, "last_failure", None)

    def authenticate(self, advocate_id: str,
                     password: str) -> AdvocateIdentity | None:
        doc = self._read(advocate_id)
        if doc is None:
            # THE COST IS PAID ANYWAY. Returning here without deriving would
            # make an unknown advocate answer in microseconds and a wrong
            # password in tens of milliseconds — the same oracle A1's second
            # NEVER forbids, wearing a stopwatch instead of a message.
            dummy().verify(password)
            self._note(advocate_id, "no such advocate")
            return None

        try:
            credential = Credential(**doc["credential"])
            verified = credential.verify(password)
        except (TypeError, ValueError, OverflowError):
            self._auth_state.last_failure = self.UNREADABLE
            dummy().verify(password)
            self._note(advocate_id, "credential record unreadable")
            return None
        if not verified:
            self._auth_state.last_failure = self.WRONG_PASSWORD
            self._note(advocate_id, "wrong password")
            return None
        self._auth_state.last_failure = None
        self._note(advocate_id, "authenticated")
        return AdvocateIdentity(**doc["identity"])

    # ------------------------------------------------------------- sessions ---

    def _session_path(self, fingerprint: str) -> Path:
        return self._sessions / f"{fingerprint}.nm"

    def _activity_path(self, fingerprint: str) -> Path:
        """When the session was last used. F-A-12.

        A FILE OF ITS OWN, NOT A FIELD REWRITTEN INTO THE SESSION RECORD. Explicit
        user activity records a checkpoint, and requests run concurrently: one
        that read the session a moment before a sign-out and then wrote it back
        with a fresh time would put the sign-out's `ended_because` back to
        `None` and revive the session. Activity is written here and the
        session record is written only by opening and ending it, so recording
        use cannot undo an end.
        """
        return self._sessions / f"{fingerprint}.active"

    def _last_activity(self, fingerprint: str) -> datetime | None:
        try:
            activity = datetime.fromisoformat(
                self._activity_path(fingerprint).read_text(encoding="utf8").strip())
            return activity if activity.utcoffset() is not None else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            # UNREADABLE IS NOT RECENT. The idle limit then runs from the last
            # time that could be read -- the issue time -- which can end a live
            # session early and cannot keep an idle one alive.
            return None

    def _record_activity(self, session: Session, now: datetime) -> None:
        """Record activity; a lost or concurrent older write can only shorten access."""
        fingerprint = session.token_fingerprint
        if session.last_active_at is not None and session.last_active_at >= now:
            return
        path = self._activity_path(fingerprint)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("x", encoding="utf8") as handle:
                handle.write(now.isoformat())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            # A LOST ACTIVITY WRITE SHORTENS A SESSION; IT NEVER LENGTHENS ONE,
            # so it must not fail the request that was entitled to run. On
            # Windows a replace refuses while another request is reading the
            # same file; the next request records it.
            self._note(session.advocate_id,
                       f"session activity not recorded: {type(exc).__name__}")
        finally:
            discard(temporary)

    def open_session(self, advocate_id: str, device: str,
                     now: datetime, *, client_label: str = '', source: str = '') -> str:
        token, session = open_session(advocate_id, device, now,
                                      client_label=client_label, source=source)
        self._write_session(session)
        return token

    def _write_session(self, session: Session) -> None:
        self._replace_advocate(self._session_path(session.token_fingerprint), {
                "token_fingerprint": session.token_fingerprint,
                "advocate_id": session.advocate_id,
                "device": session.device,
                "issued_at": session.issued_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "ended_because": session.ended_because,
                'client_label': session.client_label,
                'source': session.source,
            })

    def _read_session(self, fingerprint: str) -> Session | None:
        path = self._session_path(fingerprint)
        if not path.exists():
            return None
        try:
            # BOTH FORMS, as with the advocate record. A session sealed
            # before BK-22 keeps working until it expires rather than
            # logging its advocate out mid-matter.
            raw = path.read_bytes()
            try:
                d = json.loads(raw.decode("utf8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                d = json.loads(self._cipher.decrypt(raw).decode("utf8"))
            if d['token_fingerprint'] != fingerprint:
                return None
            issued = datetime.fromisoformat(d['issued_at'])
            expires = datetime.fromisoformat(d['expires_at'])
            if issued.utcoffset() is None or expires.utcoffset() is None:
                return None
            return Session(
                token_fingerprint=d["token_fingerprint"],
                advocate_id=d["advocate_id"],
                device=d["device"],
                issued_at=issued,
                expires_at=expires,
                ended_because=d.get("ended_because"),
                last_active_at=self._last_activity(fingerprint),
                client_label=d.get('client_label', ''),
                source=d.get('source', ''),
            )
        except Exception:  # noqa: BLE001 -- an unopenable session is not a session
            return None

    def session(self, token: str, device: str,
                now: datetime) -> Session | None:
        if not (token or "").strip():
            return None
        session = self._read_session(token_fingerprint(token))
        if session is None:
            return None

        if not session.live_at(now):
            self._note(session.advocate_id,
                       f"session refused: {session.why_not(now)}")
            return None

        # A SESSION DOES NOT TRAVEL. A1's first NEVER is that a matter list is
        # not restored on a shared or borrowed device without
        # re-authentication — and a token that works from anywhere IS that
        # restoration, however short its life.
        if session.device != (device or "unknown-device"):
            self._note(session.advocate_id,
                       "session refused: presented from a different device")
            return None

        return session

    def touch_session(self, token: str, device: str, now: datetime) -> Session | None:
        session = self.session(token, device, now)
        if session is None:
            return None
        self._record_activity(session, now)
        # A failed activity write must not promise a longer offline window.
        return self.session(token, device, now)

    def sessions_for(self, advocate_id: str) -> tuple[Session, ...]:
        """Every session issued to this advocate, live or ended. BK-31.

        BOTH, AND THE CALLER DECIDES. An advocate asking "where am I signed
        in" is asking a security question, and the answer *"one session, this
        device"* is worth nothing unless they can also see the one that ended
        an hour ago on a device they do not recognise. Filtering here would
        make the interesting half unreachable.

        A session that cannot be decoded has unknown ownership. Refuse the
        inventory rather than hiding a potentially active device from its owner.
        """
        out: list[Session] = []
        if not self._sessions.exists():
            return ()
        for path in sorted(self._sessions.glob("*.nm")):
            session = self._read_session(path.stem)
            if session is None:
                raise SessionsUnavailable('The complete session list could not be read.')
            if session.advocate_id == advocate_id:
                out.append(session)
        return tuple(out)

    def close_selected_session(self, advocate_id: str, reference: str, why: str,
                               *, except_token: str) -> str:
        keep = token_fingerprint(except_token)
        for session in self.sessions_for(advocate_id):
            if session.reference != reference:
                continue
            if session.token_fingerprint == keep:
                return 'current'
            if session.ended_because:
                return 'already_ended'
            self._write_session(replace(session, ended_because=why))
            return 'closed'
        return 'unknown'

    def close_all_sessions(self, advocate_id: str, why: str,
                           except_token: str = "") -> int:
        """End every session this advocate holds. Returns how many were ended.

        THE COUNT IS THE POINT. "Signed out everywhere" with no number is a
        claim the advocate cannot check, and the case they use this in --
        a device they no longer control -- is exactly the case where they
        need to know it worked.

        `except_token` KEEPS THE SESSION THEY ARE ASKING FROM, because
        signing an advocate out of the device they are typing on in order to
        secure the others is a control nobody uses twice.
        """
        from dataclasses import replace

        keep = token_fingerprint(except_token or "")
        ended = 0
        for session in self.sessions_for(advocate_id):
            if session.token_fingerprint == keep or session.ended_because:
                continue
            self._write_session(replace(session, ended_because=why))
            ended += 1
        return ended

    def close_session(self, token: str, why: str) -> str:
        """End a session. Returns WHICH of three things happened.

        IT RETURNED `None` AND SAID NOTHING, and `/api/logout` answered
        `{"signed_out": true}` on top of that — whether a live session had
        been ended, whether it was already closed, or whether the token named
        nothing at all. Three different facts, one confident answer, which is
        defect shape S1 on the one route whose whole job is to be believed.

        It matters because the browser believed it. BK-40's measured
        counterexample is a logout the server never received being shown to
        the advocate as a sign-in screen — and on a shared machine, that
        screen IS the protection.

            closed         a live session was ended just now
            already_ended  it existed and was already closed
            unknown        no session answers to this token

        `unknown` LEAVES THE CALLER SIGNED OUT and is still not a
        confirmation: the token cannot authenticate, and nothing was ended,
        so a session held under another token is untouched. The route reports
        both facts rather than collapsing them.
        """
        fingerprint = token_fingerprint(token or "")
        session = self._read_session(fingerprint)
        if session is None:
            return "unknown"
        if getattr(session, "ended_because", None):
            return "already_ended"
        # ENDED, NOT DELETED. A closed session that vanished would be
        # indistinguishable from one that never existed, and an operator
        # reading the audit could not tell a sign-out from a forged token.
        from dataclasses import replace
        self._write_session(replace(session, ended_because=why))
        return "closed"

    # ---------------------------------------------------------------- audit ---

    def _note(self, advocate_id: str, what: str) -> None:
        """WHY IT FAILED, where the operator can read it and the caller cannot.

        Appended in plaintext deliberately: this is an operational log about
        access attempts, not client material, and an audit nobody can read
        without the key is an audit nobody reads.
        """
        try:
            with self._audit.open("a", encoding="utf8") as fh:
                who = _one_log_field(advocate_id)
                event = _one_log_field(what)
                fh.write(f"{datetime.now().isoformat()}\t{who}\t{event}\n")
        except OSError:
            # Never fail a login because the log is unwritable. The record is
            # worth having and it is not worth locking an advocate out for.
            pass


def _one_log_field(value: object) -> str:
    """Keep untrusted identity/source text inside one tab-separated field."""
    return " ".join(str(value).replace("\t", " ").splitlines())
