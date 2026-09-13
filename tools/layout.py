"""A LAYOUT CHECK THAT CANNOT BE SWITCHED OFF BY A STYLE RULE. BK-43, BK-47.

    from tools.layout import MEASURE_JS, WIDTHS, clipped, population_problems

WHY DOCUMENT WIDTH IS NOT THE CHECK
-------------------------------------
The journey asked the page one question:

    document.documentElement.scrollWidth > document.documentElement.clientWidth

`body { overflow-x: hidden }` makes those two equal whatever the content does,
so the assertion could no longer fail. The rule is gone and
`tests/test_no_rule_hides_the_overflow.py` keeps it gone -- but REMOVING IT WAS
ONLY HALF THE DEFECT, and the smaller half.

The larger half is that document width was never the right question. An
`overflow: hidden` on ANY inner container is ordinary, correct layout -- a
scrolling rail, a clipped avatar, a table in its own box -- and a primary
control pushed outside one of those is invisible and unreachable while the
document measures exactly its viewport. Nothing about the page scrolls
sideways. The control is simply not there.

    THE QUESTION IS GEOMETRY, NOT SCROLL WIDTH: is this control's rectangle
    inside every clipping rectangle between it and the viewport?

`clipped` asks that, so it answers the same on a page that clips its overflow
and a page that does not. That is what BK-43-AC1 means by *detects
inaccessible clipped content even when overflow is hidden*.

AND VISIBLE IS NOT REACHED. BK-47
-----------------------------------
The width phase read `if page.is_visible("#rail"): return`. At 1280px the rail
is visible, so one of the three widths asserted nothing past sign-in -- and the
report showed three green rows. `population_problems` refuses that shape
directly: an action recorded as `SEEN` is not an action recorded as `RAN`, and
a width that recorded nothing at all is the loudest failure of the three.

THE POPULATION IS DECLARED, NOT DERIVED. Reading the required actions out of
what a run happened to do would let a run that did half the work declare half
the work sufficient -- the same silence `tools/journey.py`'s EXPECTED manifest
exists to refuse, one level down.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: The widths this product supports, with the viewport height each is measured
#: at. ONE DEFINITION -- the journey suites and this module's own control read
#: it rather than each carrying a tuple that drifts by one entry.
WIDTHS: tuple[tuple[int, int], ...] = ((390, 844), (768, 1024), (1280, 900))

#: WHAT AN ADVOCATE MUST BE ABLE TO DO AT EVERY WIDTH. BK-32-AC1's own list,
#: plus the preparation flows P29 to P32 added.
#:
#: Each entry is the action, not the control that performs it: a drawer, a tab
#: and a menu all satisfy "open the matter navigator", and naming the control
#: here would make the check a test of one design rather than of the product.
REQUIRED_ACTIONS: tuple[str, ...] = (
    "start a matter",
    "find another matter in the navigator",
    "switch to it",
    "reach research",
    "reach the case file",
    "reach history",
    "reach preparation",
    "reach identity",
    "sign out",
)


class Did(str, Enum):
    """Whether the action was PERFORMED, merely SEEN, or never attempted.

    `SEEN` exists because it is the state the old phase actually reached and
    reported as success. Without a name for it the population control could
    only distinguish ran from absent, and "the rail was visible" would go on
    counting as "the advocate reached the navigator".
    """

    RAN = "ran"
    SEEN = "seen"
    NOT_ATTEMPTED = "not_attempted"

    @classmethod
    def not_established(cls) -> "Did":
        return cls.NOT_ATTEMPTED

    @property
    def proves_reachable(self) -> bool:
        """ONLY `RAN`. Written once so no width decides for itself."""
        return self is Did.RAN


@dataclass(frozen=True)
class Box:
    """A rectangle in viewport coordinates."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    def intersect(self, other: "Box") -> "Box":
        return Box(left=max(self.left, other.left), top=max(self.top, other.top),
                   right=min(self.right, other.right),
                   bottom=min(self.bottom, other.bottom))

    @staticmethod
    def from_row(row: dict) -> "Box":
        return Box(left=float(row.get("left", 0.0)), top=float(row.get("top", 0.0)),
                   right=float(row.get("right", 0.0)),
                   bottom=float(row.get("bottom", 0.0)))


@dataclass(frozen=True)
class Control:
    """One primary control as the browser measured it.

    `clips` is the chain of clipping ancestors between the control and the
    viewport, OUTERMOST LAST. A control is reachable only if something of it
    survives every one of them -- an inner scroller can put it back in view,
    and an outer one can take it away again.
    """

    name: str
    rect: Box
    clips: tuple[Box, ...] = ()
    hidden: bool = False
    """`display:none`, `visibility:hidden` or `[hidden]`. A separate answer
    from clipped: a control nobody rendered and a control pushed out of its box
    are different defects with different fixes."""

    scrollable: tuple[bool, ...] = ()
    """For each clip in `clips`, whether that ancestor SCROLLS. A control
    outside a scrollable box is reachable -- the advocate scrolls to it. A
    control outside a box with `overflow: hidden` is not reachable at all, and
    that is the case document width cannot see."""

    def unreachable(self) -> str:
        """Why an advocate cannot use this control, or "".

        THE ORDER MATTERS. Hidden is reported before clipped because a hidden
        control has no meaningful rectangle, and reporting its geometry would
        send somebody looking at a layout problem that is not there.
        """
        if self.hidden:
            return (f"{self.name} is not rendered at all, so no advocate can "
                    f"reach it whatever the layout does")
        if self.rect.width <= 0 or self.rect.height <= 0:
            return (f"{self.name} measures {self.rect.width:g}x"
                    f"{self.rect.height:g}, so there is nothing to click")
        visible = self.rect
        for index, clip in enumerate(self.clips):
            scrolls = (self.scrollable[index]
                       if index < len(self.scrollable) else False)
            if scrolls:
                # A SCROLLABLE ANCESTOR IS NOT A CLIP. The advocate scrolls and
                # the control arrives; refusing this would fail every long list
                # in the product and the check would be turned off within a
                # week.
                continue
            visible = visible.intersect(clip)
            if visible.width <= 0 or visible.height <= 0:
                return (
                    f"{self.name} sits outside a container that clips its "
                    f"overflow, so it is on the page and cannot be seen or "
                    f"clicked. The document does not scroll sideways and never "
                    f"will: the clip is what removed the evidence")
        return ""


def clipped(controls: tuple[Control, ...]) -> tuple[str, ...]:
    """Every primary control an advocate cannot reach. BK-43-AC1.

    Empty is the good answer, and it is a real one: this reads geometry the
    browser measured, so an empty result means every control had a rectangle
    inside every clip between it and the viewport -- not that nothing was
    looked at. `measured` is the control that proves the population was not
    empty, and the journey asserts it.
    """
    return tuple(why for why in (c.unreachable() for c in controls) if why)


def measured(controls: tuple[Control, ...]) -> int:
    """How many controls were actually measured. A POSITIVE CONTROL ON THE
    POPULATION: `clipped(())` is empty and says nothing about the page."""
    return len(controls)


def unexecuted(executed: dict[str, Did],
               required: tuple[str, ...] = REQUIRED_ACTIONS) -> tuple[str, ...]:
    """What one width did not actually do. BK-47-AC1.

    An action absent from the mapping is `NOT_ATTEMPTED`, not permitted: the
    default that would let a phase omit a key and pass is the whole defect.
    """
    out: list[str] = []
    for action in required:
        did = executed.get(action, Did.NOT_ATTEMPTED)
        if did is Did.SEEN:
            out.append(f"{action}: the control was visible and was never used. "
                       f"Reachable is not the same as on screen, and a phase "
                       f"that returns on visibility asserts nothing")
        elif not did.proves_reachable:
            out.append(f"{action}: not attempted at this width")
    return tuple(out)


def population_problems(
        by_width: dict[int, dict[str, Did]],
        widths: tuple[tuple[int, int], ...] = WIDTHS,
        required: tuple[str, ...] = REQUIRED_ACTIONS) -> tuple[str, ...]:
    """THE WIDTH-POPULATION CONTROL. BK-47-AC1's negative control.

    *skip desktop navigation because the rail is visible* -> *the
    width-population control rejects the unexecuted route*.

    A WIDTH MISSING FROM THE MAPPING IS THE LOUDEST FAILURE, because that is
    what an early return produces: not a red row, but no row, and a runner
    counting green rows sees three of three.
    """
    out: list[str] = []
    for width, _height in widths:
        executed = by_width.get(width)
        if executed is None:
            out.append(f"{width}px executed no required action at all; a width "
                       f"that returns early leaves no row rather than a red "
                       f"one, and a report counting rows cannot see it")
            continue
        out.extend(f"{width}px -- {why}" for why in unexecuted(executed, required))
    return tuple(out)


#: THE ONE MEASUREMENT, so the browser phase and this module cannot disagree
#: about what a clipping ancestor is.
#:
#: `getComputedStyle(...).overflow` is read on every ancestor rather than on a
#: guessed container: the rule that clips may be on any of them, and the one
#: that produced BK-43 was 518 lines from the comment explaining its removal.
MEASURE_JS = """
(selectors) => {
  const out = [];
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  const renders = (el) => {
    if (!el) return false;
    const s = getComputedStyle(el);
    return !(s.display === 'none' || s.visibility === 'hidden'
             || el.hasAttribute('hidden') || el.offsetParent === null);
  };
  for (const [name, selector] of selectors) {
    // A COMMA-SEPARATED SELECTOR IS "HOWEVER THIS WIDTH OFFERS IT".
    //
    // BK-32's rule is that the navigator be REACHABLE, by some control -- a
    // drawer below 820px, the rail itself above it. `querySelector` returns
    // the FIRST match in document order, which at 1280px is the drawer toggle
    // that is correctly hidden there; measuring that reported the navigator
    // unreachable on a page where it was on screen the whole time.
    //
    // So: the first candidate that RENDERS, and the first candidate overall
    // when none does -- which keeps "nothing here is on screen" a real answer
    // rather than an omitted row.
    const candidates = String(selector).split(',').map((s) => s.trim())
      .filter(Boolean).map((s) => document.querySelector(s));
    const el = candidates.find(renders) || candidates.find(Boolean) || null;
    if (!el) { out.push({name, hidden: true, rect: {}, clips: [], scrollable: []}); continue; }
    const style = getComputedStyle(el);
    const hidden = !renders(el);
    const r = el.getBoundingClientRect();
    const clips = [];
    const scrollable = [];
    let node = el.parentElement;
    while (node) {
      const s = getComputedStyle(node);
      const o = s.overflow + ' ' + s.overflowX + ' ' + s.overflowY;
      if (/hidden|clip|scroll|auto/.test(o)) {
        const b = node.getBoundingClientRect();
        clips.push({left: b.left, top: b.top, right: b.right, bottom: b.bottom});
        scrollable.push(/scroll|auto/.test(o));
      }
      node = node.parentElement;
    }
    // THE VIEWPORT IS THE OUTERMOST CLIP and it never scrolls sideways for
    // this purpose: a control off the right edge at 390px is off the screen.
    clips.push({left: 0, top: 0, right: vw, bottom: vh});
    scrollable.push(false);
    out.push({name, hidden,
              rect: {left: r.left, top: r.top, right: r.right, bottom: r.bottom},
              clips, scrollable});
  }
  return out;
}
"""


def from_measurement(rows: list[dict]) -> tuple[Control, ...]:
    """Turn what `MEASURE_JS` returned into `Control`s."""
    return tuple(
        Control(name=str(row.get("name") or "?"),
                rect=Box.from_row(row.get("rect") or {}),
                clips=tuple(Box.from_row(c) for c in row.get("clips") or ()),
                hidden=bool(row.get("hidden")),
                scrollable=tuple(bool(s) for s in row.get("scrollable") or ()))
        for row in rows)
