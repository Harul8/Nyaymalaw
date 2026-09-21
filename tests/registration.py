"""What a registration from the register card carries besides the account details.

Implementation Plan F-A-09. The public registration route refuses an account
without the privacy consent the card collects, so every test that registers
through that route sends the same consent a person ticking both boxes sends.
Read from the domain's notice version, never retyped, so a new notice does not
leave the tests agreeing to the old one.
"""
from __future__ import annotations

import re

from nm.domain.advocate import PRIVACY_NOTICE_VERSION

CONSENT = {"notice_version": PRIVACY_NOTICE_VERSION, "agreed": True, "adult": True}


def confirm_registered(client, response):
    """Finish the real two-step signup for tests that need an active account.

    Refusals are returned unchanged. Nothing is seeded or bypassed: the served
    confirmation route must consume the code the actual outbox received.
    """
    if response.status_code != 202:
        return response
    body = response.json()
    assert body['state'] == 'confirmation_required'
    email = body['email']
    assert client.directory.identity(email) is None, 'signup activated before mailbox proof'
    messages = [m for m in client.outbox.messages_for(email)
                if m['purpose'] == 'email-confirmation']
    assert messages, 'confirmation was not queued'
    code = re.search(r'\b[0-9]{6}\b', messages[-1]['text']).group()
    return client.post('/api/register/confirm', json={
        'email': email, 'code': code, 'flow': body['flow']})
