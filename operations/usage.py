"""Read an account's usage of the paid AI service, add to its allowance, or total every call's cost,
from the trusted operator host (owner decision O24, plan AN.17).

No HTTP endpoint exposes the grant. Possession of the deployment's storage is the operator boundary,
not a signed-in account. Until payment exists (later, by UPI), a grant here is how an allowance grows
past its 30-cent trial - for the owner's own development account, for example.

    python operations/usage.py status --account advocate@chambers.in
    python operations/usage.py grant --account advocate@chambers.in --usd 5 --operator rahul --reason "development"
    python operations/usage.py totals
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()


def dollars(micro: int) -> str:
    return f"USD {Decimal(micro) / 1_000_000:.6f}"


def micro_usd(text: str) -> int:
    """A dollar amount as millionths of a dollar, refused unless it is exact to the millionth."""
    try:
        amount = Decimal(text) * 1_000_000
    except InvalidOperation as exc:
        raise ValueError("the amount is a number of US dollars, such as 5 or 0.25") from exc
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("the amount is a number of US dollars, to at most six decimal places")
    return int(amount)


def described(standing: dict) -> dict:
    return {"granted": dollars(standing["granted"]), "spent": dollars(standing["spent"]),
            "left": f"{standing['left']}%", "last_notice_shown": standing["noticed"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="what an account was given, has spent and has left")
    status.add_argument("--account", required=True)
    grant = commands.add_parser("grant", help="add usage to an account's allowance")
    grant.add_argument("--account", required=True)
    grant.add_argument("--usd", required=True, help="the amount to add, in US dollars")
    grant.add_argument("--operator", required=True)
    grant.add_argument("--reason", required=True)
    commands.add_parser("totals", help="every call's cost: overall, by model and by outcome")
    args = parser.parse_args(argv)

    from nm.app.composition import Application

    usage = Application().usage
    try:
        if args.command == "status":
            print(json.dumps(described(usage.standing(args.account)), indent=2))
        elif args.command == "grant":
            standing = usage.grant(args.account, micro_usd(args.usd),
                                   note=f"{args.operator.strip()}: {args.reason.strip()}"[:200])
            print(json.dumps(described(standing), indent=2))
        else:
            totals = usage.totals()
            for group in ("by_model", "by_outcome"):
                for row in totals[group]:
                    row["cost"] = dollars(row.pop("micro_usd"))
            totals["granted"], totals["cost"] = dollars(totals["granted"]), dollars(totals.pop("micro_usd"))
            print(json.dumps(totals, indent=2))
    except ValueError as exc:
        parser.exit(2, f"Nothing was changed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
