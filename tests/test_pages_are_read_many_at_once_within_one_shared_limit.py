"""Pages are read many at once, within one limit shared by every upload (plan AN.25, P3).

A 20-page scan was read four pages at a time - five waves of about 15 seconds - and every upload had a pool of four of its own, so
several uploads together could ask the AI service for any number of reads. One document now reads up to AT_ONCE pages together and
every document in the process together never more than ALL_AT_ONCE; a read that fails or is refused gives its place back. The numbers
are set without a paid run and are to be confirmed by a bounded live one. No private data: pages are synthetic.
"""
import threading
import time

import pytest

from nm.core_engine import page_reading
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage

pytestmark = pytest.mark.class_a


class Counting:
    """A page reader that records how many reads are in flight at once, holding each for a moment."""

    def __init__(self, hold=0.05, fail=()):
        self.hold, self.fail, self.now, self.most, self.lock = hold, set(fail), 0, 0, threading.Lock()

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        number = int(prompt.user.split()[1])
        with self.lock:
            self.now += 1
            self.most = max(self.most, self.now)
        try:
            time.sleep(self.hold)
            if number in self.fail:
                raise ProviderUnavailable("scripted outage")
            return ModelResult(text=None, data={"text": f"Page {number}.", "readable": "all", "note": ""}, tier=tier,
                               provider="scripted", model="page-model-1", usage=Usage(1, 1, 0.0), latency_ms=1)
        finally:
            with self.lock:
                self.now -= 1


def images(count):
    return {number: b"\xff\xd8\xff" for number in range(1, count + 1)}


def test_one_document_reads_up_to_eight_pages_together_and_no_more():
    model = Counting()
    read, calls = page_reading.read_pages(model, "scan.pdf", images(20))
    assert page_reading.AT_ONCE == 8 and model.most == 8
    assert sorted(read) == list(range(1, 21)) and all(page["state"] == "read" for page in read.values()) and len(calls) == 20


def test_every_document_in_the_process_shares_one_limit(monkeypatch):
    monkeypatch.setattr(page_reading, "_SHARED", threading.BoundedSemaphore(10))
    model = Counting(hold=0.1)
    threads = [threading.Thread(target=page_reading.read_pages, args=(model, f"scan{n}.pdf", images(8))) for n in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert model.most == 10, "three documents of eight pages are 24 reads wanted at once; the shared limit allows 10"


def test_a_read_that_fails_gives_its_place_back_and_the_others_are_read():
    shared = threading.BoundedSemaphore(4)
    page_reading._SHARED, kept = shared, page_reading._SHARED
    try:
        read, _ = page_reading.read_pages(Counting(fail=[2, 5]), "scan.pdf", images(6))
        assert [read[n]["state"] for n in range(1, 7)] == ["read", "unread", "read", "read", "unread", "read"]
        assert all(shared.acquire(blocking=False) for _ in range(4)), "every place was given back"
        assert not shared.acquire(blocking=False)
    finally:
        page_reading._SHARED = kept


def test_the_limits_are_the_ones_the_plan_names_and_the_shared_one_is_not_smaller_than_one_documents():
    assert page_reading.AT_ONCE <= page_reading.ALL_AT_ONCE == 16
