"""Explicit, transactional alignment for the previous PostgreSQL schema.

No startup hook calls this tool. Existing legacy values remain stored.
"""
import argparse
import asyncio
import json
import re

from sqlalchemy import inspect, text


async def align_schema(connection, schema="public"):
    if connection.dialect.name != "postgresql":
        raise ValueError("This alignment requires PostgreSQL.")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError("Invalid schema name.")
    quote = connection.dialect.identifier_preparer.quote_identifier
    prefix = quote(schema) + "."
    names = ("blacklist", "performance_seats", "payments")
    # Serialize inspection and DDL with concurrent writers; transaction owns locks.
    await connection.execute(text("LOCK TABLE " + ", ".join(prefix + quote(n) for n in names) + " IN ACCESS EXCLUSIVE MODE"))
    def describe(sync):
        inspector = inspect(sync)
        return {name: {
            "columns": {c["name"]: c for c in inspector.get_columns(name, schema=schema)},
            "pk": inspector.get_pk_constraint(name, schema=schema),
        } for name in names}
    info = await connection.run_sync(describe)
    columns = info["blacklist"]["columns"]
    if not {"jti_token", "expired_at"} <= columns.keys():
        raise ValueError("Unsupported blacklist columns; no changes applied.")
    pk = info["blacklist"]["pk"]
    if pk["constrained_columns"] not in (["black_id"], ["jti_token"]):
        raise ValueError("Unsupported blacklist primary key; no changes applied.")
    allowed = {"jti_token", "expired_at", "black_id", "user_id", "created_at"}
    if any(not c["nullable"] and c.get("default") is None for n, c in columns.items() if n not in allowed):
        raise ValueError("Unknown required blacklist column; no changes applied.")
    blacklist = prefix + quote("blacklist")
    invalid = await connection.scalar(text(
        f"SELECT EXISTS (SELECT 1 FROM {blacklist} WHERE jti_token IS NULL OR length(jti_token) > 500) "
        f"OR EXISTS (SELECT 1 FROM {blacklist} GROUP BY jti_token HAVING count(*) > 1)"
    ))
    if invalid:
        raise ValueError("Null, duplicate, or oversized token IDs require manual resolution; no rows removed.")
    for name in ("performance_seats", "payments"):
        if "reserv_id" not in info[name]["columns"]:
            raise ValueError("Missing reservation link; no changes applied.")
    changes = []
    # No CASCADE: an unexpected FK referencing the old key aborts the transaction.
    if pk["constrained_columns"] == ["black_id"]:
        await connection.execute(text(f"ALTER TABLE {blacklist} DROP CONSTRAINT {quote(pk['name'])}"))
        await connection.execute(text(f"ALTER TABLE {blacklist} ADD PRIMARY KEY (jti_token)"))
        changes.append("blacklist primary key aligned to jti_token")
    for legacy in ("black_id", "user_id"):
        if (legacy in columns and not columns[legacy]["nullable"]
                and not columns[legacy].get("identity")):
            await connection.execute(text(f"ALTER TABLE {blacklist} ALTER COLUMN {quote(legacy)} DROP NOT NULL"))
            changes.append(f"blacklist.{legacy} retained as nullable legacy data")
    token_type = columns["jti_token"]["type"]
    if getattr(token_type, "length", None) != 500:
        await connection.execute(text(f"ALTER TABLE {blacklist} ALTER COLUMN jti_token TYPE VARCHAR(500)"))
        changes.append("blacklist.jti_token capacity aligned")
    for name in ("performance_seats", "payments"):
        if not info[name]["columns"]["reserv_id"]["nullable"]:
            await connection.execute(text(f"ALTER TABLE {prefix + quote(name)} ALTER COLUMN reserv_id DROP NOT NULL"))
            changes.append(f"{name}.reserv_id permits unlinked rows")
    return changes


async def run(args):
    # Import the existing connection configuration only in the explicit CLI path.
    from asyncticket.shared.core.database import engine
    try:
        if engine.url.database != args.expected_database:
            raise ValueError("Database name does not match --expected-database.")
        if engine.url.host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("This tool only applies to an explicitly named local database.")
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            changes = await align_schema(connection)
            if not args.apply:
                await connection.rollback()
        print(json.dumps({"applied": args.apply, "changes": changes}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--apply", action="store_true", help="Commit the alignment; otherwise roll it back.")
    asyncio.run(run(parser.parse_args()))
