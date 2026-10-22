"""Idempotent synthetic demo loader for the fixed demo owner. Reads DATABASE_URL only."""

from lazyresearch.application.demo_data import DEMO_REQUEST_KEY, home_battery_inputs
from lazyresearch.bootstrap import build_workspace


def main() -> None:
    work = build_workspace()
    receipt = work.add(DEMO_REQUEST_KEY, home_battery_inputs())
    print(f"Demo sources submitted: {len(receipt.entries)} (idempotent; safe to rerun).")
    print("No analyses, feedback or research results were created.")


if __name__ == "__main__":
    main()
