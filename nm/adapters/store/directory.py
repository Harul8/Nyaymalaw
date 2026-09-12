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

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime
from io import BufferedRandom
from pathlib import Path

from nm.adapters.store.file_store import _Cipher
from nm.domain.advocate import (
    AccountSecurity,
    AdvocateIdentity,
    Credential,
    Enrolment,
    Invitation,
    ReauthenticationProof,
    RecoveryCodeRecord,
    RecoveryResult,
    Session,
    advocate_id_is_storage_safe,
    canonical_id,
    dummy,
    new_invitation,
    new_reauthentication_proof,
    new_recovery_codes,
    open_session,
    recovery_code_matches,
    token_fingerprint,
)
from nm.domain.traceability import implements
from nm.infrastructure.cleanup import discard
from nm.ports.directory import (  # noqa: F401
    AccountBusy,
    AlreadyEnrolled,
    InvitationRefused,
    ProofRefused,
)

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

#: THE SAME SENTENCE FOR EVERY ROTATION REFUSAL, on the rule above.
#:
#: Expired proof, spent proof, another session's proof, a credential that moved
#: and a recovery set that moved are five facts, and a caller holding a stolen
#: session must not be able to tell them apart -- "your password changed since"
#: is precisely the thing such a caller wants to know. `_note` records which.
#:
#: IT ALSO SAYS WHAT TO DO NEXT, because an advocate told only "refused" in the
#: middle of securing their account will assume the product is broken.
_ROTATION_REFUSED = (
    "Your recovery codes were not replaced and the ones you already hold still "
    "work. Confirm your password again and retry; if you have just changed "
    "your password or replaced these codes elsewhere, reload first.")


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
    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._advocates = self._root / "advocates"
        self._sessions = self._root / "sessions"
        self._audit = self._root / "auth.log"
        self._attempts = self._root / "attempts.log"
        self._invitations = self._root / "invitations"
        self._used_invitations = self._invitations / "used"
        self._recovery_locks = self._root / "recovery-locks"
        self._proofs = self._root / "reauth-proofs"
        self._advocates.mkdir(parents=True, exist_ok=True)
        self._sessions.mkdir(parents=True, exist_ok=True)
        self._proofs.mkdir(parents=True, exist_ok=True)
        self._invitations.mkdir(parents=True, exist_ok=True)
        self._used_invitations.mkdir(parents=True, exist_ok=True)
        self._recovery_locks.mkdir(parents=True, exist_ok=True)
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
                          now: datetime) -> tuple[AdvocateIdentity, tuple[str, ...]]:
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
            codes = self.enrol(Enrolment(identity=invitation.identity,
                                         credential=credential, created_at=now))
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
        return invitation.identity, codes

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
        """THE ONLY PLACE THE GENERATION COUNTERS ARE PERSISTED. BK-31-AC20.

        Every write that touches `credential` or `recovery_codes` comes
        through here and must SAY what happened to each generation. The
        alternative -- bumping a counter wherever the material is written --
        looks like the same rule and is not: `recover` writes the whole
        `recovery_codes` list to mark ONE code spent, and a rule keyed on the
        write would call that a replaced set and lose every rotation racing a
        recovery for no reason.

        Replaced-set and spent-code are different facts. Making the caller
        pass the transition puts that judgement at the site, where it is
        reviewable, instead of inside a heuristic that reads the same either
        way.
        """
        blob.update(security.as_dict())
        self._replace_advocate(path, blob)

    def _replace_advocate(self, path: Path, blob: dict) -> None:
        """Replace one account record without exposing a partial JSON write."""
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

    def enrol(self, enrolment: Enrolment) -> tuple[str, ...]:
        path = self._advocate_path(enrolment.identity.id)
        codes, recovery = new_recovery_codes()
        blob = {
            "identity": enrolment.identity.as_dict(),
            "credential": self._credential_record(enrolment.credential),
            "recovery_codes": [record.as_dict() for record in recovery],
            "created_at": enrolment.created_at.isoformat(),
            # A NEW ACCOUNT IS GENERATION 1 ON BOTH, not 0. Zero is what an
            # account enrolled before this model existed reads as, and the two
            # must be distinguishable: a proof minted against a legacy account
            # records 0, and the account's first mutation moving it to 1 is
            # exactly the change that proof must be refused for.
            **AccountSecurity(credential_generation=1,
                              recovery_generation=1).as_dict(),
        }
        # IN THE OPEN, DELIBERATELY (BK-22). The credential is an scrypt
        # hash with its salt and cost -- scrypt exists so that such a hash
        # can be stored where it can be read. Sealing it AS WELL made
        # signing in depend on `NM_MATTER_KEY`, a key that is meant to
        # rotate, and rotating it locked every advocate out.
        #
        # Client material is not here and is not affected: matters,
        # transcripts and metrics keep the matter key.
        created = False
        try:
            # Exclusive creation owns the one-identity decision on disk. A
            # prior `exists()` check left a last-writer-wins interval between
            # the check and this write when two valid invitations arrived at
            # different worker processes.
            with path.open("x", encoding="utf8") as handle:
                created = True
                handle.write(json.dumps(blob, indent=2))
        except FileExistsError as exc:
            raise AlreadyEnrolled(
                f"{enrolment.identity.id} is already enrolled. Overwriting "
                f"would replace a credential without anyone deciding to.") from exc
        except Exception:
            # A failed first write must not leave a corrupt record that reads
            # as an enrolled advocate and locks out a corrected retry.
            if created:
                # A ROLLBACK, not housekeeping: the write is what failed, so
                # nothing was delivered and the name must go. It still routes
                # through `discard` so a failure here cannot replace the
                # exception that says what actually went wrong.
                discard(path)
            raise
        return codes

    # ------------------------------------------------------------- recovery ---

    def _recovery_lock_path(self, advocate_id: str) -> Path:
        digest = hashlib.sha256(canonical_id(advocate_id).encode("utf8")).hexdigest()
        return self._recovery_locks / f"{digest}.lock"

    def _claim_recovery(self, advocate_id: str) -> _AccountClaim | None:
        """Own account access across workers; the OS retires crashed claims."""
        path = self._recovery_lock_path(advocate_id)
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

    @staticmethod
    def _recovery_records(doc: dict | None) -> tuple[RecoveryCodeRecord, ...]:
        if not doc:
            return ()
        try:
            return tuple(RecoveryCodeRecord(**item)
                         for item in doc.get("recovery_codes", ()))
        except (TypeError, ValueError):
            return ()

    @staticmethod
    def _matching_recovery(
            records: tuple[RecoveryCodeRecord, ...], code: str,
            ) -> RecoveryCodeRecord | None:
        """Check every digest so the matching record's position leaks nothing."""
        matched = None
        for record in records:
            if recovery_code_matches(record, code):
                matched = record
        return matched

    def ensure_recovery_codes(self, advocate_id: str,
                              now: datetime) -> tuple[str, ...]:
        """Give a pre-recovery-build advocate one set on their next valid login."""
        path = self._advocate_path(advocate_id)
        doc = self._read(advocate_id)
        if doc is None or "recovery_codes" in doc:
            return ()
        claim = self._claim_recovery(advocate_id)
        if claim is None:
            return ()
        try:
            doc = self._read(advocate_id)
            if doc is None or "recovery_codes" in doc:
                return ()
            codes, records = new_recovery_codes()
            doc["recovery_codes"] = [record.as_dict() for record in records]
            doc["recovery_codes_issued_at"] = now.isoformat()
            # A SET WAS CREATED WHERE THERE WAS NONE. That is a replacement as
            # far as anything holding an expectation is concerned.
            self._write_account(
                path, doc, AccountSecurity.read(doc).with_new_recovery_set())
            self._note(advocate_id, "recovery codes issued after authentication")
            return codes
        finally:
            claim.release()

    def authenticate_and_open_session(
            self, advocate_id: str, password: str, device: str, now: datetime,
            ) -> tuple[AdvocateIdentity, str, tuple[str, ...]] | None:
        """Keep successful authentication and session issue on one generation."""
        if not self._advocate_path(advocate_id).exists():
            # Unknown public input still pays the normal dummy derivation and
            # audit path, but must not create an unbounded population of
            # persistent lock artifacts.
            self.authenticate(advocate_id, password)
            return None
        claim = self._claim_recovery(advocate_id)
        if claim is None:
            raise AccountBusy("account access is already changing")
        try:
            identity = self.authenticate(advocate_id, password)
            if identity is None:
                return None
            doc = self._read(identity.id)
            if doc is None:
                return None
            recovery_codes: tuple[str, ...] = ()
            if "recovery_codes" not in doc:
                recovery_codes, records = new_recovery_codes()
                doc["recovery_codes"] = [record.as_dict() for record in records]
                doc["recovery_codes_issued_at"] = now.isoformat()
                self._write_account(
                    self._advocate_path(identity.id), doc,
                    AccountSecurity.read(doc).with_new_recovery_set())
                self._note(identity.id, "recovery codes issued after authentication")
            token = self.open_session(identity.id, device, now)
            return identity, token, recovery_codes
        finally:
            claim.release()

    def recover(self, advocate_id: str, code: str, credential: Credential,
                now: datetime) -> RecoveryResult:
        """Consume one code, replace the credential and end every session."""
        canonical = canonical_id(advocate_id)
        doc = self._read(canonical)
        records = self._recovery_records(doc)
        # Unknown and legacy-without-codes still pay the whole digest loop.
        if not records:
            _, dummy_records = new_recovery_codes()
            self._matching_recovery(dummy_records, code)
            self._note(canonical, "recovery refused: unknown or no code set")
            return RecoveryResult(False)
        if self._matching_recovery(records, code) is None:
            self._note(canonical, "recovery refused: wrong or used code")
            return RecoveryResult(False)

        claim = self._claim_recovery(canonical)
        if claim is None:
            self._note(canonical, "recovery refused: another attempt in progress")
            return RecoveryResult(False)
        try:
            # Re-read under the shared claim. Another directory may have used
            # this code between the optimistic check and exclusive creation.
            doc = self._read(canonical)
            records = self._recovery_records(doc)
            matched = self._matching_recovery(records, code)
            if doc is None or matched is None:
                self._note(canonical, "recovery refused: wrong or used code")
                return RecoveryResult(False)

            # End old grants before changing the door. A failed session write
            # aborts recovery and no success is reported; a false success here
            # would leave precisely the compromised device recovery exists for.
            ended = self.close_all_sessions(canonical, "password recovered")
            updated = [
                RecoveryCodeRecord(
                    id=item.id, salt=item.salt, hash=item.hash,
                    used_at=now.isoformat() if item.id == matched.id else item.used_at,
                ).as_dict()
                for item in records
            ]
            doc["credential"] = self._credential_record(credential)
            doc["recovery_codes"] = updated
            doc["credential_changed_at"] = now.isoformat()
            # THE CREDENTIAL MOVED AND THE RECOVERY SET DID NOT. `updated`
            # rewrites the whole list to stamp `used_at` on ONE record: same
            # set, one member spent. Bumping the recovery generation here
            # would make every rotation racing a recovery fail as stale when
            # the set it means to replace is precisely the one still there.
            self._write_account(
                self._advocate_path(canonical), doc,
                AccountSecurity.read(doc).with_new_credential())
            self._note(canonical, f"recovery succeeded; {ended} sessions ended")
            return RecoveryResult(True, ended)
        finally:
            claim.release()

    # -------------------------------------------- fresh authentication ---

    def _proof_path(self, fingerprint: str) -> Path:
        return self._proofs / f"{fingerprint}.nm"

    def _write_proof(self, proof: ReauthenticationProof) -> None:
        """Sealed, like every other record that names an advocate.

        WHAT IS NOT HERE IS THE POINT: the proof token itself. Only its
        fingerprint, exactly as with sessions and invitations, so a stolen
        store is not a set of spendable authorisations.
        """
        self._proof_path(proof.token_fingerprint).write_bytes(
            self._cipher.encrypt(json.dumps({
                "token_fingerprint": proof.token_fingerprint,
                "advocate_id": proof.advocate_id,
                "session_fingerprint": proof.session_fingerprint,
                "credential_generation": proof.security.credential_generation,
                "recovery_generation": proof.security.recovery_generation,
                "issued_at": proof.issued_at.isoformat(),
                "expires_at": proof.expires_at.isoformat(),
                "consumed_at": proof.consumed_at.isoformat()
                               if proof.consumed_at else None,
            }, indent=2).encode("utf8")))

    def _read_proof(self, fingerprint: str) -> ReauthenticationProof | None:
        path = self._proof_path(fingerprint)
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            try:
                data = json.loads(self._cipher.decrypt(raw).decode("utf8"))
            except Exception:  # noqa: BLE001 -- pre-seal records stay readable
                data = json.loads(raw.decode("utf8"))
        except Exception:  # noqa: BLE001 -- an unreadable proof is not a proof
            return None
        consumed = data.get("consumed_at")
        return ReauthenticationProof(
            token_fingerprint=data["token_fingerprint"],
            advocate_id=data["advocate_id"],
            session_fingerprint=data["session_fingerprint"],
            security=AccountSecurity.read(data),
            issued_at=datetime.fromisoformat(data["issued_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            consumed_at=datetime.fromisoformat(consumed) if consumed else None,
        )

    def account_security(self, advocate_id: str) -> int | None:
        """The current recovery generation, or None if it cannot be read.

        THREE STATES. An unreadable or absent account returns None rather than
        0: a client told "generation 0" would send that as its expectation and
        a legacy account really on 0 would accept it, so an unreadable record
        would authorise the very replacement it cannot verify.
        """
        doc = self._read(canonical_id(advocate_id))
        if doc is None:
            return None
        return AccountSecurity.read(doc).recovery_generation

    def reauthenticate(self, advocate_id: str, password: str,
                       session_token: str, device: str,
                       now: datetime, *, source: str = "reauthenticate") -> str | None:
        """Prove the current password again, inside this session. BK-31-AC20.

        `None` COVERS FOUR DIFFERENT FAILURES and says which to nobody: a wrong
        password, a session that is not live, a session belonging to another
        advocate, and a session presented from another device. A signed-in
        advocate who could tell them apart could use this to probe the roster,
        which is A1's second NEVER arriving one layer up.

        The derivation runs even when the session is already disqualified, for
        the same reason `authenticate` runs it for an unknown advocate: an
        answer returned in 0.2ms where the other takes 80ms is an oracle
        whatever the response body says.
        """
        session = self.session(session_token, device, now)
        identity = self.authenticate(advocate_id, password)
        if identity is None:
            self.note_failure(canonical_id(advocate_id), source, now)
            return None
        if session is None or canonical_id(session.advocate_id) != identity.id:
            self._note(identity.id,
                       "reauthentication refused: no live session of this "
                       "advocate on this device")
            self.note_failure(identity.id, source, now)
            return None
        security = AccountSecurity.read(self._read(identity.id))
        token, proof = new_reauthentication_proof(
            identity.id, session.token_fingerprint, security, now)
        self._write_proof(proof)
        self._note(identity.id,
                   f"fresh authentication proof issued, expires "
                   f"{proof.expires_at.isoformat()}")
        return token

    def rotate_recovery_codes(self, advocate_id: str, proof_token: str,
                              session_token: str, device: str,
                              expected_recovery_generation: int,
                              now: datetime, *,
                              source: str = "rotate-recovery-codes") -> tuple[str, ...]:
        """Replace the whole set atomically. The new codes, once. BK-31-AC20.

        THE PROOF IS SPENT BEFORE THE SET IS REPLACED, and the order is the
        decision. Spend-then-replace can lose a rotation to an I/O failure and
        the advocate authenticates again -- an inconvenience. Replace-then-spend
        can leave a live proof beside a replaced set, and that is a second
        rotation an attacker gets for free. Fail closed.

        SESSION POLICY: the rotating session survives and every other session
        of this advocate ends. Replacing the last-resort credential is a
        security event, and an attacker holding another live session should not
        keep it across one -- while signing the advocate out of the device they
        are typing on is a control nobody uses twice. `close_all_sessions`
        already draws that line for `sessions/revoke`.
        """
        canonical = canonical_id(advocate_id)
        session = self.session(session_token, device, now)
        if session is None or canonical_id(session.advocate_id) != canonical:
            self._note(canonical, "recovery rotation refused: no live session "
                                  "of this advocate on this device")
            self.note_failure(canonical, source, now)
            raise ProofRefused(_ROTATION_REFUSED)

        claim = self._claim_recovery(canonical)
        if claim is None:
            raise AccountBusy("account access is already changing")
        try:
            doc = self._read(canonical)
            security = AccountSecurity.read(doc)
            proof = self._read_proof(token_fingerprint((proof_token or "").strip()))
            if doc is None:
                why = "the account record could not be read"
            elif proof is None:
                why = "no such proof"
            else:
                why = proof.why_not(
                    advocate_id=canonical,
                    session_fingerprint=session.token_fingerprint,
                    security=security, now=now)
            if why is None and expected_recovery_generation != security.recovery_generation:
                # THE CALLER'S OWN EXPECTATION, checked separately from the
                # proof's. The proof says nothing moved since it was minted;
                # this says the client was looking at the same set it is asking
                # to replace. A client rendered from a stale read would
                # otherwise silently replace a set it never showed anybody.
                why = (f"the caller expected recovery generation "
                       f"{expected_recovery_generation} and the account is on "
                       f"{security.recovery_generation}")
            if why is not None:
                self._note(canonical, f"recovery rotation refused: {why}")
                self.note_failure(canonical, source, now)
                raise ProofRefused(_ROTATION_REFUSED)

            from dataclasses import replace

            self._write_proof(replace(proof, consumed_at=now))
            codes, records = new_recovery_codes()
            doc["recovery_codes"] = [record.as_dict() for record in records]
            doc["recovery_codes_issued_at"] = now.isoformat()
            self._write_account(self._advocate_path(canonical), doc,
                                security.with_new_recovery_set())
            ended = self.close_all_sessions(
                canonical, "recovery codes replaced", except_token=session_token)
            # THE EVENT, NEVER THE CODES. `_note` writes one audit line and the
            # codes exist only in the value returned above.
            self._note(canonical,
                       f"recovery codes replaced; generation "
                       f"{security.recovery_generation} -> "
                       f"{security.recovery_generation + 1}; "
                       f"{ended} other sessions ended")
            return codes
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
        path = self._advocate_path(advocate_id)
        self._auth_state.last_failure = self.UNKNOWN
        if not path.exists():
            return None
        raw = path.read_bytes()
        try:
            # PLAIN FIRST, SEALED SECOND. Records written before BK-22 are
            # encrypted, and this reads both -- so no account breaks and
            # there is no window in which sign-in is down. A record is
            # rewritten in the open the next time it is written.
            try:
                doc = json.loads(raw.decode("utf8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                doc = json.loads(self._cipher.decrypt(raw).decode("utf8"))
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

        NONE MEANS THE LIMITER COULD NOT RUN -- not that there were no
        failures. The caller opens the door and reports it, because
        refusing every sign-in would be a self-inflicted outage; what it
        must not do is treat unreadable as clean, which is S1.
        """
        if not self._attempts.exists():
            return ((), ())
        try:
            raw = self._attempts.read_text(encoding="utf8",
                                           errors="replace")
        except OSError:
            return None

        wanted = canonical_id(advocate_id)
        mine: list = []
        here: list = []
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            stamp, who, where = parts
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when < since:
                continue
            if who == wanted:
                mine.append(when)
            if where == source:
                here.append(when)
        return (tuple(mine), tuple(here))

    def note_failure(self, advocate_id: str, source: str,
                     now: datetime) -> None:
        """One line per failed attempt. Never raises: a limiter that can
        break a sign-in is worse than one that misses a count.

        NO CLIENT MATERIAL. A timestamp, a folded id and a source -- the
        same shape the auth log beside it has held since slice 1.
        """
        try:
            with self._attempts.open("a", encoding="utf8") as fh:
                who = _one_log_field(canonical_id(advocate_id))
                where = _one_log_field(source)
                fh.write(f"{now.isoformat()}\t{who}\t{where}\n")
        except OSError:
            pass

    def limiter_available(self) -> bool:
        """Whether the attempt log can be written. Reported at /api/health
        so a limiter that is not running is visible BEFORE an incident.
        """
        try:
            self._attempts.touch(exist_ok=True)
            return True
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

        credential = Credential(**doc["credential"])
        if not credential.verify(password):
            self._auth_state.last_failure = self.WRONG_PASSWORD
            self._note(advocate_id, "wrong password")
            return None
        self._auth_state.last_failure = None
        self._note(advocate_id, "authenticated")
        return AdvocateIdentity(**doc["identity"])

    # ------------------------------------------------------------- sessions ---

    def _session_path(self, fingerprint: str) -> Path:
        return self._sessions / f"{fingerprint}.nm"

    def open_session(self, advocate_id: str, device: str,
                     now: datetime) -> str:
        token, session = open_session(advocate_id, device, now)
        self._write_session(session)
        return token

    def _write_session(self, session: Session) -> None:
        self._session_path(session.token_fingerprint).write_bytes(
            json.dumps({
                "token_fingerprint": session.token_fingerprint,
                "advocate_id": session.advocate_id,
                "device": session.device,
                "issued_at": session.issued_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "ended_because": session.ended_because,
            }, indent=2).encode("utf8"))

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
        except Exception:  # noqa: BLE001 -- an unopenable session is not a session
            return None
        return Session(
            token_fingerprint=d["token_fingerprint"],
            advocate_id=d["advocate_id"],
            device=d["device"],
            issued_at=datetime.fromisoformat(d["issued_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            ended_because=d.get("ended_because"),
        )

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

    def sessions_for(self, advocate_id: str) -> tuple[Session, ...]:
        """Every session issued to this advocate, live or ended. BK-31.

        BOTH, AND THE CALLER DECIDES. An advocate asking "where am I signed
        in" is asking a security question, and the answer *"one session, this
        device"* is worth nothing unless they can also see the one that ended
        an hour ago on a device they do not recognise. Filtering here would
        make the interesting half unreachable.

        A SESSION THAT WILL NOT DECODE IS NOT DROPPED SILENTLY -- it is
        counted by the caller through `unreadable`, because a device list
        missing a row is the one thing worse than no device list.
        """
        out: list[Session] = []
        if not self._sessions.exists():
            return ()
        for path in sorted(self._sessions.glob("*.nm")):
            session = self._read_session(path.stem)
            if session is not None and session.advocate_id == advocate_id:
                out.append(session)
        return tuple(out)

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
