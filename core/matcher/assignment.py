"""Global assignment - conflict resolution across candidate links (spec §14).

Suggestions are locally computed and will conflict (one document proposed in
several groups). Sort all candidate links by
(tier ASC, confidence DESC, cardinality ASC, deterministic tiebreak on hash),
greedily accept while marking member documents consumed within each plane-pair,
and supersede losers with a pointer to the winner. Stable sort, explicit
tiebreak: non-deterministic ordering is a build defect.
"""
from __future__ import annotations

from .common import TIER_RANK, BAND_RANK


class _UF:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def connected(self, a, b):
        return self.find(a) == self.find(b)


def assign(links: list[dict]) -> dict:
    order = sorted(links, key=lambda l: (
        TIER_RANK[l["tier"]],
        BAND_RANK.get(l["confidence_band"], 3),
        -l["confidence"],
        l["cardinality"],
        l["link_id"],
    ))

    uf = _UF()
    used_in_pair: dict = {}          # pair -> {row_id: link_id}
    accepted = []
    superseded = []

    for link in order:
        pair = link["pair"]
        claimed = used_in_pair.setdefault(pair, {})
        conflict = next((rid for rid in link["all_ids"] if rid in claimed), None)
        if conflict is not None:
            link["match_status"] = "SUPERSEDED"
            link["superseded_by"] = claimed[conflict]
            superseded.append(link)
            continue
        # redundant: both endpoints already tied together
        ids = link["all_ids"]
        if len(ids) >= 2 and all(uf.find(i) == uf.find(ids[0]) for i in ids) \
                and all(i in uf.parent for i in ids):
            link["match_status"] = "REDUNDANT"
            superseded.append(link)
            continue
        # accept
        for rid in ids:
            claimed[rid] = link["link_id"]
        for rid in ids[1:]:
            uf.union(ids[0], rid)
        link["match_status"] = "ACCEPTED"
        accepted.append(link)

    # component id per document
    comp_of = {}
    for link in accepted:
        root = uf.find(link["all_ids"][0])
        for rid in link["all_ids"]:
            comp_of[rid] = uf.find(rid)
    return {"accepted": accepted, "superseded": superseded, "uf": uf, "comp_of": comp_of}
