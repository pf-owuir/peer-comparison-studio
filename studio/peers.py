"""Peer groups: fixed lists or rules over IPEDS directory fields.

Each group is a YAML file in config/peer_groups/. Resolving a group against a
directory year returns its members plus the reason each one is included, so
every comparison can say exactly who the peers were and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from studio import directory as dirmod
from studio.paths import peer_group_dir


@dataclass
class PeerGroup:
    id: str
    name: str
    type: str  # "fixed" or "rules"
    benchmark: str
    description: str = ""
    source: str = ""
    short_name: str = ""  # shown in menus; falls back to name
    members: dict[str, str] = field(default_factory=dict)  # fixed: UNITID -> expected name
    rules: dict = field(default_factory=dict)  # rules: HD field -> allowed values or {min, max}
    exclude: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path) -> "PeerGroup":
        data = yaml.safe_load(Path(path).read_text())
        members = {str(m["unitid"]): m["name"] for m in data.get("members", [])}
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            benchmark=str(data["benchmark"]),
            description=data.get("description", ""),
            short_name=data.get("short_name", ""),
            source=data.get("source", ""),
            members=members,
            rules=data.get("rules", {}) or {},
            exclude=[str(x) for x in data.get("exclude", [])],
            include=[str(x) for x in data.get("include", [])],
        )

    @property
    def label(self) -> str:
        return self.short_name or self.name

    def resolve(self, directory: pd.DataFrame) -> pd.DataFrame:
        """Return member institutions (benchmark excluded) with a 'reason' column."""
        if self.type == "fixed":
            dirmod.verify(directory, self.members)
            ids = list(self.members)
            reason = f"Listed in {self.source or self.name}"
            out = directory.loc[ids, ["UNITID", "INSTNM", "CITY", "STABBR"]].copy()
            out["reason"] = reason
        elif self.type == "rules":
            mask = pd.Series(True, index=directory.index)
            parts = []
            for fld, cond in self.rules.items():
                if fld not in directory.columns:
                    raise KeyError(f"Peer group {self.id}: field {fld} is not in the directory")
                col = directory[fld]
                if isinstance(cond, dict):
                    num = pd.to_numeric(col, errors="coerce")
                    if "min" in cond:
                        mask &= num >= cond["min"]
                    if "max" in cond:
                        mask &= num <= cond["max"]
                    parts.append(f"{fld} {cond.get('min', '')}-{cond.get('max', '')}")
                else:
                    allowed = {str(v) for v in (cond if isinstance(cond, list) else [cond])}
                    mask &= col.isin(allowed)
                    parts.append(f"{fld} in {sorted(allowed)}")
            ids = list(directory.index[mask])
            ids += [i for i in self.include if i not in ids]
            out = directory.loc[ids, ["UNITID", "INSTNM", "CITY", "STABBR"]].copy()
            out["reason"] = "Matches rules: " + "; ".join(parts)
            out.loc[out.index.isin(self.include), "reason"] = "Added by hand (include list)"
        else:
            raise ValueError(f"Peer group {self.id}: unknown type {self.type!r}")

        drop = set(self.exclude) | {self.benchmark}
        out = out[~out.index.isin(drop)]
        out.attrs["group"] = self.id
        out.attrs["directory"] = directory.attrs.get("source", "")
        return out.sort_values("INSTNM")


def load_all(group_dir: Path | None = None) -> dict[str, PeerGroup]:
    group_dir = Path(group_dir) if group_dir else peer_group_dir()
    groups = {}
    for path in sorted(group_dir.glob("*.yaml")):
        g = PeerGroup.from_file(path)
        if g.id in groups:
            raise ValueError(f"Duplicate peer group id {g.id}")
        groups[g.id] = g
    return groups


CUSTOM_PREFIX = "custom_"


def slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in text.lower())
    return "_".join(p for p in out.split("_") if p)[:40] or "group"


def save_custom(name: str, benchmark: str, members: dict[str, str], description: str = "",
                group_dir: Path | None = None, source: str = "") -> Path:
    """Write a fixed peer group built in the app to config/peer_groups/custom_<name>.yaml.

    members maps UNITID -> name exactly as in the IPEDS directory, so the
    build's UNITID check passes. An existing custom group of the same name is
    replaced; the built-in groups can never be overwritten from here.
    """
    group_dir = Path(group_dir) if group_dir else peer_group_dir()
    name = " ".join(name.split())
    if not name:
        raise ValueError("The group needs a name")
    if not members:
        raise ValueError("The group needs at least one member")
    gid = CUSTOM_PREFIX + slug(name)
    data = {
        "id": gid,
        "name": name,
        "short_name": name[:36],
        "type": "fixed",
        "benchmark": int(benchmark),
        "description": description,
        "source": source or "Custom group built in the app",
        "members": [{"unitid": int(u), "name": n} for u, n in sorted(members.items(), key=lambda kv: kv[1])
                    if str(u) != str(benchmark)],
    }
    path = group_dir / f"{gid}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return path


def delete_custom(group_id: str, group_dir: Path | None = None) -> None:
    if not group_id.startswith(CUSTOM_PREFIX):
        raise ValueError(f"{group_id} is a built-in group; only custom groups can be deleted here")
    group_dir = Path(group_dir) if group_dir else peer_group_dir()
    (group_dir / f"{group_id}.yaml").unlink(missing_ok=True)
