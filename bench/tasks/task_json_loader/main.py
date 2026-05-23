import json

def load_config(path):
    with open(path) as f:
        data = json.load(f)
    if "database" not in data:
        return {}
    cfg = data["database"]
    result = {"host": cfg.get("host", "localhost")}
    result["port"] = cfg.get("port")
    result["name"] = cfg["name"]
    return result

def validate_config(cfg):
    if not cfg:
        return False
    if "port" not in cfg:
        return True
    if cfg["port"] is None:
        return True
    if not isinstance(cfg["port"], int):
        return True
    return True
