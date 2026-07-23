"""Tier 4 - subset-sum (1:N and N:1), spec §11.2 / §11.3.

Given an anchor with a target tax amount, find subsets of candidate documents
on the other plane whose tax_minor sums to target within tolerance. Tax is the
primary search key. Exact meet-in-the-middle for blocks <= cap; heuristic
greedy + local search for larger blocks (confidence then capped at Medium).
"""
from __future__ import annotations

import itertools
import random


def _tol(cfg, k, target):
    return max(cfg.rounding_abs_minor_per_doc * max(k, 1),
               int(round(cfg.relative_tol * abs(target))))


def enumerate_subsets_exact(candidates: list[dict], target: int, cfg,
                            max_card: int, cap: int) -> list[list[dict]]:
    """All subsets (cardinality 1..max_card) of candidates whose tax_minor sums
    within tol of target. Meet-in-the-middle. Returns up to `cap` subsets,
    sorted deterministically. This is what makes ambiguity detection exact."""
    n = len(candidates)
    if n == 0:
        return []
    tol = _tol(cfg, max_card, target)

    half = n // 2
    left = candidates[:half]
    right = candidates[half:]

    def subsets(items, base_offset):
        acc = []
        for k in range(0, min(max_card, len(items)) + 1):
            for combo in itertools.combinations(range(len(items)), k):
                s = sum(items[i]["tax_minor"] for i in combo)
                acc.append((s, tuple(base_offset + i for i in combo)))
        return acc

    left_subsets = subsets(left, 0)
    right_subsets = subsets(right, half)
    right_subsets.sort(key=lambda t: t[0])
    right_sums = [t[0] for t in right_subsets]

    import bisect
    results = []
    seen = set()
    for lsum, lidx in left_subsets:
        lo = target - lsum - tol
        hi = target - lsum + tol
        i = bisect.bisect_left(right_sums, lo)
        while i < len(right_sums) and right_sums[i] <= hi:
            ridx = right_subsets[i][1]
            idx = tuple(sorted(lidx + ridx))
            i += 1
            if not idx or len(idx) > max_card:
                continue
            if idx in seen:
                continue
            seen.add(idx)
            results.append(idx)
            if len(results) >= cap * 4:  # gather generously, trim after sort
                break
        if len(results) >= cap * 4:
            break

    # deterministic ordering: prefer smaller cardinality, then tighter sum,
    # then lexicographic on row_id
    def sort_key(idx):
        s = sum(candidates[i]["tax_minor"] for i in idx)
        ids = tuple(candidates[i]["row_id"] for i in idx)
        return (len(idx), abs(s - target), ids)

    results.sort(key=sort_key)
    return [[candidates[i] for i in idx] for idx in results[:cap]]


def heuristic_search(candidates: list[dict], target: int, cfg,
                     max_card: int) -> list[dict] | None:
    """Greedy descending + local search for large blocks. Reproducible via a
    fixed seed from config. Returns one best subset (confidence capped Medium)."""
    m = cfg.engine["matching"]
    rng = random.Random(m["heuristic_seed"])
    cand = sorted(candidates, key=lambda d: -d["tax_minor"])
    tol = _tol(cfg, max_card, target)

    def residual(subset):
        return abs(sum(d["tax_minor"] for d in subset) - target)

    best = None
    best_res = None
    for _ in range(m["heuristic_restarts"]):
        subset = []
        total = 0
        order = cand[:]
        rng.shuffle(order)
        order.sort(key=lambda d: -d["tax_minor"])
        for d in order:
            if len(subset) >= max_card:
                break
            if total + d["tax_minor"] <= target + tol:
                subset.append(d)
                total += d["tax_minor"]
        # local search: swap moves
        budget = m["heuristic_iteration_budget"] // max(1, m["heuristic_restarts"])
        for _ in range(budget):
            if residual(subset) <= tol:
                break
            in_ids = {d["row_id"] for d in subset}
            out = [d for d in cand if d["row_id"] not in in_ids]
            if not subset or not out:
                break
            i = rng.randrange(len(subset))
            j = rng.randrange(len(out))
            trial = subset[:i] + subset[i + 1:] + [out[j]]
            if len(trial) <= max_card and residual(trial) < residual(subset):
                subset = trial
        r = residual(subset)
        if best_res is None or r < best_res:
            best, best_res = subset, r
    if best is not None and best_res is not None and best_res <= tol and best:
        return best
    return None
