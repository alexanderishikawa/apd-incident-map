from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apd.client import ApdClient
from apd.db import Database
from apd.export import export_site_data
from apd.geocode import Geocoder
from apd.pull import pull_historical, pull_last_days
from apd.seed import seed_from_export


def _default_db() -> Path:
    return Path("data/incidents.sqlite")


def _default_export() -> Path:
    return Path("site/public/data")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apd", description="APD incident ETL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pull = sub.add_parser("pull", help="Pull incidents from APD search2.cfm")
    p_pull.add_argument("--db", type=Path, default=_default_db())
    p_pull.add_argument("--last-days", type=int, default=None)
    p_pull.add_argument("--historical", action="store_true")
    p_pull.add_argument("--max-windows", type=int, default=None)
    p_pull.add_argument("--no-resume", action="store_true")

    p_geo = sub.add_parser("geocode", help="Geocode pending addresses (Nominatim)")
    p_geo.add_argument("--db", type=Path, default=_default_db())
    p_geo.add_argument("--budget", type=int, default=300)
    p_geo.add_argument(
        "--retry-fails",
        action="store_true",
        help="Re-attempt addresses previously cached as fail",
    )

    p_exp = sub.add_parser("export", help="Export JSON for the static site")
    p_exp.add_argument("--db", type=Path, default=_default_db())
    p_exp.add_argument("--out", type=Path, default=_default_export())

    p_seed = sub.add_parser(
        "seed",
        help="Load incidents.json or incidents.json.gz into SQLite (noop if DB nonempty)",
    )
    p_seed.add_argument("--db", type=Path, default=_default_db())
    p_seed.add_argument("--data", type=Path, default=_default_export())
    p_seed.add_argument(
        "--force",
        action="store_true",
        help="Seed even if DB already has rows",
    )

    args = parser.parse_args(argv)

    if args.cmd == "pull":
        if not args.historical and args.last_days is None:
            args.last_days = 7
        db = Database(args.db)
        with ApdClient() as client:
            if args.historical:
                results = pull_historical(
                    db,
                    client,
                    max_windows=args.max_windows,
                    resume=not args.no_resume,
                )
            else:
                results = pull_last_days(db, client, last_days=args.last_days)
        print(json.dumps({"results": results, "total_incidents": db.count_incidents()}, indent=2))
        db.close()
        return 0

    if args.cmd == "geocode":
        db = Database(args.db)
        geo = Geocoder(db)
        try:
            stats = geo.run(budget=args.budget, retry_fails=args.retry_fails)
        finally:
            geo.close()
            db.close()
        print(json.dumps(stats, indent=2))
        return 0

    if args.cmd == "export":
        db = Database(args.db)
        meta = export_site_data(db, args.out)
        db.close()
        print(json.dumps(meta, indent=2))
        return 0

    if args.cmd == "seed":
        db = Database(args.db)
        stats = seed_from_export(
            db, args.data, skip_if_nonempty=not args.force
        )
        db.close()
        print(json.dumps(stats, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
