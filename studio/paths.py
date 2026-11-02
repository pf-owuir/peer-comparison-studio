from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CONFIG_DIR = ROOT / "config"
PEER_GROUP_DIR = CONFIG_DIR / "peer_groups"
METRICS_FILE = CONFIG_DIR / "metrics.yaml"
