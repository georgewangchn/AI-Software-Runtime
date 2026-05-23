import json
import tempfile
import os
from main import load_config, validate_config

def _write_temp(data):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name

def test_load_valid_config():
    path = _write_temp({"database": {"host": "db1", "port": 5432, "name": "mydb"}})
    try:
        cfg = load_config(path)
        assert cfg["host"] == "db1"
        assert cfg["port"] == 5432
        assert cfg["name"] == "mydb"
    finally:
        os.unlink(path)

def test_missing_port_invalid():
    path = _write_temp({"database": {"host": "db1", "name": "mydb"}})
    try:
        cfg = load_config(path)
        assert not validate_config(cfg)
    finally:
        os.unlink(path)

def test_null_port_invalid():
    path = _write_temp({"database": {"host": "db1", "port": None, "name": "mydb"}})
    try:
        cfg = load_config(path)
        assert not validate_config(cfg)
    finally:
        os.unlink(path)

def test_string_port_invalid():
    path = _write_temp({"database": {"host": "db1", "port": "5432", "name": "mydb"}})
    try:
        cfg = load_config(path)
        assert not validate_config(cfg)
    finally:
        os.unlink(path)

def test_missing_database_section():
    path = _write_temp({"app": {"name": "test"}})
    try:
        cfg = load_config(path)
        assert cfg == {}
        assert not validate_config(cfg)
    finally:
        os.unlink(path)
