"""
Pricing constants live in exactly one module.

`src/bidmath` is the config module for money. Every fee, increment, tax rate and
bid fraction is defined there once, with a comment saying why it is that number.
A second copy somewhere else is not a duplicate, it is a FUTURE DISAGREEMENT:
when the house changes its buyer's premium, one of the two copies gets updated.

This is not hypothetical here. `scripts/run_aug22_cycle.py` carried its own
`ABSENTEE_FEE = 0.15` and multiplied by a literal `1.15` twice; the pipeline and
the single-photo runner each open-coded `max(5.0, bid * 0.35)`. Every one of
those is the $5 increment or the 35% bid fraction, re-typed away from the
constant that documents it.

The guard is deliberately narrow. It looks for the specific NUMERIC VALUES that
are pricing policy, in `.py` files, outside `src/bidmath`, ignoring comments and
anything that is plainly not money — a CSS `rgba(...)`, a Chrome user-agent
string, matplotlib coordinates, an ffmpeg filter. A guard that cries wolf gets
suppressed, and a suppressed guard protects nothing.
"""

import ast
import re
from pathlib import Path

import pytest

from src.bidmath import (
    ABSENTEE_FEE, BASE_BID_FRACTION_HIGH, BASE_BID_FRACTION_LOW, BID_INCREMENT,
    HOUSE_MINIMUM_BID, WI_SALES_TAX_RATE,
)

# The value -> what it means -> what to use instead.
PRICING_VALUES = {
    ABSENTEE_FEE:            ("absentee fee", "ABSENTEE_FEE"),
    1 + ABSENTEE_FEE:        ("hammer + absentee fee", "all_in_cost()"),
    BASE_BID_FRACTION_LOW:   ("low bid fraction", "bid_fraction_for()"),
    BASE_BID_FRACTION_HIGH:  ("high bid fraction", "bid_fraction_for()"),
    WI_SALES_TAX_RATE:       ("WI sales tax", "WI_SALES_TAX_RATE"),
}
# BID_INCREMENT and HOUSE_MINIMUM_BID are both 5.0 and 5.0 is an ordinary number
# elsewhere (a timeout, a retry count, a plot coordinate). Only flag it where it
# is doing pricing work — see _is_pricing_five.
FIVE = {BID_INCREMENT, HOUSE_MINIMUM_BID}

# Names that already mean something in src/bidmath. Re-binding one in another
# module is the clearest possible drift: two constants, one name, one truth.
CANONICAL_NAMES = {
    "ABSENTEE_FEE", "BID_INCREMENT", "WI_SALES_TAX_RATE", "DEFAULT_TAX_RATE",
    "BASE_BID_FRACTION_LOW", "BASE_BID_FRACTION_HIGH", "HOUSE_MINIMUM_BID",
}

SEARCH_ROOTS = (Path("src"), Path("scripts"), Path("demo"))
CANONICAL = Path("src/bidmath")

# Files whose numbers are not money. Kept explicit and short.
EXEMPT = {
    Path("scripts/generate_architecture_diagram.py"),   # matplotlib geometry
    Path("scripts/assemble_final.py"),                  # ffmpeg filter graph
    Path("scripts/build_video.py"),                     # ffmpeg / timing
    Path("scripts/make_title_cards.mjs"),
}


def _python_files():
    for root in SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*.py")):
            if CANONICAL in f.parents or f in EXEMPT or "__pycache__" in f.parts:
                continue
            yield f


def _pricing_literals(path):
    """(lineno, value, meaning, use_instead) for pricing constants doing pricing work.

    Drift has a shape, and matching the shape rather than the bare value is what
    keeps this guard credible. A pricing number is drift when it is:

      * an operand of ARITHMETIC on a line that is about money —
        `round(max_bid * 1.15, 2)`, `max(5.0, bid * 0.35)`; or
      * assigned to a name that SHADOWS a canonical constant —
        `ABSENTEE_FEE = 0.15` in a script.

    It is NOT drift when the same value is a dict entry, a keyword argument, or
    a recorded fact. `Confidence.MEDIUM: 0.35` is a ranking weight,
    `temperature=0.4` is model config, and `"hammer": 5.00` in the July 11
    benchmark is what the auctioneer actually charged — history, not policy.
    Flagging those trains people to ignore the guard.
    """
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError:
        return
    lines = path.read_text().splitlines()

    def flag(node):
        v = round(node.value, 6)
        if v in PRICING_VALUES:
            return (node.lineno, v) + PRICING_VALUES[v]
        if v in FIVE:
            return (node.lineno, v, "bid increment / house minimum", "BID_INCREMENT")
        return None

    def is_pricing_const(n):
        return (isinstance(n, ast.Constant) and isinstance(n.value, float)
                and (round(n.value, 6) in PRICING_VALUES or round(n.value, 6) in FIVE))

    seen = set()
    for node in ast.walk(tree):
        hits = []
        # arithmetic on a money line
        if isinstance(node, ast.BinOp):
            hits += [o for o in (node.left, node.right) if is_pricing_const(o)]
        # max()/min() floors and ceilings
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("max", "min")):
            hits += [a for a in node.args if is_pricing_const(a)]
        for h in hits:
            if _money_line(lines, h.lineno) and (h.lineno, h.col_offset) not in seen:
                seen.add((h.lineno, h.col_offset))
                got = flag(h)
                if got:
                    yield got
        # a name that shadows a canonical constant
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Name) and t.id in CANONICAL_NAMES
                        and is_pricing_const(node.value)):
                    if (node.value.lineno, node.value.col_offset) not in seen:
                        seen.add((node.value.lineno, node.value.col_offset))
                        got = flag(node.value)
                        if got:
                            yield got


_MONEY_CONTEXT = re.compile(
    r"bid|hammer|max_bid|all_in|increment|snap|price|floor|start", re.I)


def _money_line(lines, lineno):
    """True when the line this literal sits on is doing pricing work."""
    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    return bool(_MONEY_CONTEXT.search(line))


def _all_drift():
    out = []
    for f in _python_files():
        for lineno, value, meaning, use in _pricing_literals(f):
            out.append((f, lineno, value, meaning, use))
    return out


class TestPricingConstantsHaveExactlyOneHome:
    def test_no_module_outside_bidmath_hardcodes_a_pricing_constant(self):
        drift = _all_drift()
        if drift:
            report = "\n".join(
                f"  {f}:{ln}  {v}  ({meaning}) -> use {use}"
                for f, ln, v, meaning, use in drift)
            pytest.fail(
                f"{len(drift)} pricing constant(s) hardcoded outside "
                f"src/bidmath.\nA second copy is a future disagreement: when "
                f"the house changes a fee, only one copy gets updated.\n"
                f"{report}")

    def test_the_guard_can_actually_see_drift(self, tmp_path):
        """A guard that cannot fail protects nothing. Prove it fires."""
        f = tmp_path / "fake.py"
        f.write_text("def all_in(bid):\n    return bid * 1.15\n")
        found = list(_pricing_literals(f))
        assert found, "guard failed to flag a hardcoded 1.15"

    def test_the_guard_ignores_comments_and_docstrings(self, tmp_path):
        """Explaining WHY the fee is 15% is documentation, not drift."""
        f = tmp_path / "fake.py"
        f.write_text('"""The absentee fee is 0.15 of hammer."""\n'
                     "# 15% -> 0.15, published by the house\n"
                     "def f():\n    return 1\n")
        assert list(_pricing_literals(f)) == []

    def test_the_guard_ignores_numbers_that_are_not_money(self, tmp_path):
        f = tmp_path / "fake.py"
        f.write_text("TIMEOUT = 5.0\nRETRIES = 5.0\ncoord = (4.0, 5.0)\n")
        assert list(_pricing_literals(f)) == []

    def test_the_guard_ignores_coincidental_values_in_non_pricing_roles(self):
        """0.35 as a confidence weight, 0.4 as a model temperature, and 5.00 as
        a recorded hammer price are not policy constants. Flagging them trains
        people to ignore the guard, which is worse than not having one."""
        for path, lineno in ((Path("src/appraisal/__init__.py"), 39),
                             (Path("src/appraiser/engine.py"), 362)):
            if not path.is_file():
                continue
            assert lineno not in [ln for ln, *_ in _pricing_literals(path)]

    def test_a_shadowing_assignment_is_always_drift(self, tmp_path):
        f = tmp_path / "fake.py"
        f.write_text("ABSENTEE_FEE = 0.15\n")
        assert list(_pricing_literals(f)), "re-binding a canonical name is drift"

    def test_bidmath_itself_is_never_flagged(self):
        """The canonical module is where these numbers belong."""
        assert not any(CANONICAL in f.parents for f, *_ in _all_drift())
