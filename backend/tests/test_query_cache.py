from __future__ import annotations

from agente.cache.consultas import QueryResultCache
from agente.utils.cypher_guard import GuardedCypher, guard_cypher

SAFE_QUERY = "MATCH (n:Node) RETURN n.name AS name LIMIT $limit"


def guarded_query(limit: int = 10) -> GuardedCypher:
    """Build a query through the same validation seam used by the executors."""
    return guard_cypher(SAFE_QUERY, {"limit": limit})


def test_cache_hit_returns_defensive_rows() -> None:
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    cache.put(guarded_query(), [{"name": "Analista"}])

    first = cache.get(guarded_query())
    assert first == [{"name": "Analista"}]
    assert first is not None
    first[0]["name"] = "Mutated"
    assert cache.get(guarded_query()) == [{"name": "Analista"}]


def test_cache_expiry_removes_entry() -> None:
    now = [100.0]
    cache = QueryResultCache(ttl_seconds=10, max_entries=4, clock=lambda: now[0])
    query = guarded_query()
    cache.put(query, [{"name": "Analista"}])

    now[0] = 109.9
    assert cache.get(query) == [{"name": "Analista"}]
    now[0] = 110.0
    assert cache.get(query) is None
    assert len(cache) == 0


def test_cache_separates_queries_and_parameters() -> None:
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    other_query = guard_cypher(
        "MATCH (n:OtherNode) RETURN n.name AS name LIMIT $limit",
        {"limit": 10},
    )
    cache.put(guarded_query(10), [{"value": "ten"}])
    cache.put(guarded_query(20), [{"value": "twenty"}])
    cache.put(other_query, [{"value": "other"}])

    assert cache.get(guarded_query(10)) == [{"value": "ten"}]
    assert cache.get(guarded_query(20)) == [{"value": "twenty"}]
    assert cache.get(other_query) == [{"value": "other"}]


def test_cache_evicts_least_recently_used_entry_at_bound() -> None:
    cache = QueryResultCache(ttl_seconds=60, max_entries=2)
    first = guarded_query(1)
    second = guarded_query(2)
    third = guarded_query(3)
    cache.put(first, [{"value": 1}])
    cache.put(second, [{"value": 2}])
    assert cache.get(first) == [{"value": 1}]

    cache.put(third, [{"value": 3}])

    assert len(cache) == 2
    assert cache.get(first) == [{"value": 1}]
    assert cache.get(second) is None
    assert cache.get(third) == [{"value": 3}]


def test_cache_rejects_unsafe_and_non_json_queries() -> None:
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    unsafe = GuardedCypher(
        "MATCH (n:Node) SET n.name = $name RETURN n.name AS name LIMIT $limit",
        {"name": "secret", "limit": 1},
        1,
    )
    non_json = GuardedCypher(SAFE_QUERY, {"limit": object()}, 10)

    cache.put(unsafe, [{"name": "must not cache"}])
    cache.put(non_json, [{"name": "must not cache"}])
    cache.put(guarded_query(), [{"value": object()}])

    assert len(cache) == 0
    assert cache.get(unsafe) is None
    assert cache.get(non_json) is None
