"""Retired raw-match rewrite script; existing database rows are left intact."""


async def backfill():
    raise RuntimeError(
        "Raw match storage is disabled. The full-match agent backfill has been retired."
    )


if __name__ == "__main__":
    raise SystemExit(
        "Raw match storage is disabled. The full-match agent backfill has been retired."
    )
