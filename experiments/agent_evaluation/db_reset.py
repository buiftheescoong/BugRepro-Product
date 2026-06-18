"""
MongoDB snapshot/restore helpers for experiment runs.

Usage:
    python db_reset.py snapshot
    python db_reset.py restore
    python db_reset.py check --root-url http://qairline.ui-testing.io.vn/
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
REBUGGER_DIR = REPO_ROOT / "rebugger-agent"
CONFIG_PATH = THIS_DIR / "config.yaml"

DEFAULT_RESET_CONFIG = {
    "enabled": False,
    "hosts": ["qairline.ui-testing.io.vn"],
    "mongo_uri_env": "QAIRLINE_MONGO_URI",
    "database_env": "QAIRLINE_DB_NAME",
    "fixture_dir": "../data/qairline_seed",
    "exclude_collections": [],
    "drop_extra_collections": True,
    "fail_on_error": True,
}


class DbResetError(RuntimeError):
    pass


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_reset_config(config: dict | None = None) -> dict:
    config = config or load_config()
    reset_config = dict(DEFAULT_RESET_CONFIG)
    reset_config.update(config.get("db_reset") or {})
    reset_config["hosts"] = [h.lower() for h in reset_config.get("hosts", [])]
    reset_config["exclude_collections"] = set(reset_config.get("exclude_collections") or [])
    reset_config["fixture_dir"] = resolve_fixture_dir(reset_config["fixture_dir"])
    return reset_config


def resolve_fixture_dir(fixture_dir: str) -> Path:
    path = Path(fixture_dir)
    if path.is_absolute():
        return path
    return (THIS_DIR / path).resolve()


def load_experiment_env() -> None:
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REBUGGER_DIR / ".env", override=True)


def should_reset_for_url(root_url: str, reset_config: dict) -> bool:
    if not reset_config.get("enabled", False):
        return False
    host = (urlparse(root_url).hostname or "").lower()
    return host in reset_config.get("hosts", [])


def _get_database(reset_config: dict):
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise DbResetError("Missing dependency: pymongo. Install with `pip install pymongo`.") from exc

    load_experiment_env()
    mongo_uri = os.getenv(reset_config["mongo_uri_env"])
    database_name = os.getenv(reset_config["database_env"])
    if not mongo_uri:
        raise DbResetError(f"Missing env var: {reset_config['mongo_uri_env']}")
    if not database_name:
        raise DbResetError(f"Missing env var: {reset_config['database_env']}")

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    return client, client[database_name], database_name


def _json_util():
    try:
        from bson import json_util
    except ImportError as exc:
        raise DbResetError("Missing dependency: pymongo. Install with `pip install pymongo`.") from exc
    return json_util


def _collection_fixture_files(fixture_dir: Path) -> list[Path]:
    return sorted(p for p in fixture_dir.glob("*.json") if p.name != "_metadata.json")


def create_snapshot(reset_config: dict | None = None) -> dict:
    reset_config = reset_config or get_reset_config()
    json_util = _json_util()
    fixture_dir = reset_config["fixture_dir"]
    fixture_dir.mkdir(parents=True, exist_ok=True)

    client, db, database_name = _get_database(reset_config)
    try:
        collections = [
            name for name in sorted(db.list_collection_names())
            if not name.startswith("system.") and name not in reset_config["exclude_collections"]
        ]
        stats = {}
        for name in collections:
            docs = list(db[name].find({}))
            with open(fixture_dir / f"{name}.json", "w", encoding="utf-8") as f:
                f.write(json_util.dumps(docs, ensure_ascii=False, indent=2))
            stats[name] = len(docs)

        metadata = {
            "database": database_name,
            "collections": stats,
            "exclude_collections": sorted(reset_config["exclude_collections"]),
        }
        with open(fixture_dir / "_metadata.json", "w", encoding="utf-8") as f:
            f.write(json_util.dumps(metadata, ensure_ascii=False, indent=2))
        return {"database": database_name, "fixture_dir": str(fixture_dir), "collections": stats}
    finally:
        client.close()


def restore_snapshot(reset_config: dict | None = None) -> dict:
    reset_config = reset_config or get_reset_config()
    json_util = _json_util()
    fixture_dir = reset_config["fixture_dir"]
    fixture_files = _collection_fixture_files(fixture_dir)
    if not fixture_files:
        raise DbResetError(
            f"No fixture JSON files found in {fixture_dir}. "
            "Run `python db_reset.py snapshot` after preparing the seed database."
        )

    client, db, database_name = _get_database(reset_config)
    try:
        fixture_collections = {p.stem for p in fixture_files}
        excluded = reset_config["exclude_collections"]

        if reset_config.get("drop_extra_collections", True):
            for name in db.list_collection_names():
                if name.startswith("system.") or name in excluded or name in fixture_collections:
                    continue
                db.drop_collection(name)

        stats = {}
        for fixture_file in fixture_files:
            collection_name = fixture_file.stem
            if collection_name in excluded:
                continue

            with open(fixture_file, "r", encoding="utf-8") as f:
                docs = json_util.loads(f.read())
            if not isinstance(docs, list):
                raise DbResetError(f"Fixture must contain a JSON array: {fixture_file}")

            collection = db[collection_name]
            collection.delete_many({})
            if docs:
                collection.insert_many(docs, ordered=False)
            stats[collection_name] = len(docs)

        return {"database": database_name, "fixture_dir": str(fixture_dir), "collections": stats}
    finally:
        client.close()


def reset_before_bug(root_url: str, config: dict, logger=None, context: dict | None = None) -> dict | None:
    reset_config = get_reset_config(config)
    context = context or {}
    if not should_reset_for_url(root_url, reset_config):
        return None

    try:
        result = restore_snapshot(reset_config)
        message = (
            "QAirline MongoDB reset completed: "
            f"{len(result['collections'])} collections restored"
        )
        if logger:
            logger.info(message, extra={"data": {**context, **result}})
        else:
            print(message)
        return result
    except Exception as exc:
        message = f"QAirline MongoDB reset failed: {exc}"
        if logger:
            logger.error(message, exc_info=True, extra={"data": context})
        if reset_config.get("fail_on_error", True):
            raise
        print(f"[WARN] {message}")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot or restore QAirline MongoDB seed data.")
    parser.add_argument("command", choices=["snapshot", "restore", "check"])
    parser.add_argument("--root-url", default="http://qairline.ui-testing.io.vn/")
    args = parser.parse_args()

    config = load_config()
    reset_config = get_reset_config(config)

    try:
        if args.command == "check":
            print(f"enabled={reset_config['enabled']}")
            print(f"fixture_dir={reset_config['fixture_dir']}")
            print(f"should_reset={should_reset_for_url(args.root_url, reset_config)}")
        elif args.command == "snapshot":
            result = create_snapshot(reset_config)
            print(f"Snapshot saved to {result['fixture_dir']}")
            for name, count in result["collections"].items():
                print(f"  {name}: {count} docs")
        elif args.command == "restore":
            result = restore_snapshot(reset_config)
            print(f"Restored {len(result['collections'])} collections in {result['database']}")
            for name, count in result["collections"].items():
                print(f"  {name}: {count} docs")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
