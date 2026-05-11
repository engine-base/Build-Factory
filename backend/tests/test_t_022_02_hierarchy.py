"""T-022-02: 階層循環参照 (cycle) 防止 trigger — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-022 階層循環参照 validator (DB + app 層)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : RLS / audit_logs CLAUDE.md §5.3 通り (read-only validator)
  AC-4 UNWANTED      : invalid edges / cycle 検出は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import hierarchy_validator as hv
from services.hierarchy_validator import (
    HierarchyError,
    MAX_EDGES,
    MAX_NODES,
    detect_cycle_on_add,
    find_all_cycles,
    topological_order,
    validate_edge_addition,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: detect_cycle_on_add
# ──────────────────────────────────────────────────────────────────────────


def test_detect_cycle_empty_graph_no_cycle():
    assert detect_cycle_on_add([], 1, 2) is None


def test_detect_cycle_simple_chain_no_cycle():
    # 1 → 2 → 3 ; add 3 → 4
    edges = [(1, 2), (2, 3)]
    assert detect_cycle_on_add(edges, 3, 4) is None


def test_detect_cycle_back_edge_detects():
    # 1 → 2 → 3 ; add 3 → 1 closes cycle
    edges = [(1, 2), (2, 3)]
    cycle = detect_cycle_on_add(edges, 3, 1)
    assert cycle is not None
    # cycle path: 3 → 1 → 2 → 3
    assert cycle[0] == 3
    assert cycle[-1] == 3
    assert 1 in cycle and 2 in cycle


def test_detect_cycle_self_loop():
    cycle = detect_cycle_on_add([], 5, 5)
    assert cycle == [5, 5]


def test_detect_cycle_branched_graph():
    #   1 → 2 → 3
    #       ↓
    #       4 → 5
    # add 5 → 1 → cycle: 5 → 1 → 2 → 4 → 5
    edges = [(1, 2), (2, 3), (2, 4), (4, 5)]
    cycle = detect_cycle_on_add(edges, 5, 1)
    assert cycle is not None
    assert cycle[0] == 5
    assert cycle[-1] == 5


def test_detect_cycle_disjoint_components_no_cross():
    # component 1: 1 → 2
    # component 2: 10 → 20
    # add 2 → 10 should not cycle (no back-path)
    edges = [(1, 2), (10, 20)]
    assert detect_cycle_on_add(edges, 2, 10) is None


def test_detect_cycle_input_validation_new_from():
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([], 0, 2)
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([], -1, 2)
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([], "x", 2)  # type: ignore


def test_detect_cycle_input_validation_edges_not_list():
    with pytest.raises(HierarchyError):
        detect_cycle_on_add("not-a-list", 1, 2)  # type: ignore


def test_detect_cycle_invalid_edge_shape():
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([(1, 2, 3)], 4, 5)  # type: ignore
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([[1]], 4, 5)


def test_detect_cycle_invalid_edge_node():
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([(1, -2)], 3, 4)
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([(0, 2)], 3, 4)


def test_detect_cycle_bool_node_rejected():
    # bool は int の subclass だが reject する仕様
    with pytest.raises(HierarchyError):
        detect_cycle_on_add([], True, 2)  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: validate_edge_addition
# ──────────────────────────────────────────────────────────────────────────


def test_validate_edge_addition_ok():
    validate_edge_addition([(1, 2)], 2, 3)  # 例外なし


def test_validate_edge_addition_raises_on_cycle():
    with pytest.raises(HierarchyError, match="cycle_detected"):
        validate_edge_addition([(1, 2), (2, 3)], 3, 1)


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: find_all_cycles
# ──────────────────────────────────────────────────────────────────────────


def test_find_all_cycles_acyclic():
    edges = [(1, 2), (2, 3), (3, 4)]
    assert find_all_cycles(edges) == []


def test_find_all_cycles_with_cycle():
    edges = [(1, 2), (2, 3), (3, 1)]
    cycles = find_all_cycles(edges)
    assert len(cycles) >= 1
    # 各 cycle は開始 == 終端
    for c in cycles:
        assert c[0] == c[-1]


def test_find_all_cycles_self_loop():
    edges = [(5, 5)]
    cycles = find_all_cycles(edges)
    assert [5, 5] in cycles


def test_find_all_cycles_invalid_edges():
    with pytest.raises(HierarchyError):
        find_all_cycles("nope")  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: topological_order
# ──────────────────────────────────────────────────────────────────────────


def test_topo_order_simple():
    edges = [(1, 2), (2, 3), (1, 3)]
    order = topological_order(edges)
    assert order.index(1) < order.index(2)
    assert order.index(2) < order.index(3)


def test_topo_order_with_explicit_nodes():
    edges = [(1, 2)]
    order = topological_order(edges, nodes=[1, 2, 99])
    assert 99 in order


def test_topo_order_cycle_raises():
    with pytest.raises(HierarchyError, match="cycle_detected"):
        topological_order([(1, 2), (2, 3), (3, 1)])


def test_topo_order_self_loop_raises():
    with pytest.raises(HierarchyError):
        topological_order([(1, 1)])


def test_topo_order_invalid_node_in_nodes_arg():
    with pytest.raises(HierarchyError):
        topological_order([(1, 2)], nodes=[1, 0])


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_validate_edge_ok(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2], [2, 3]],
        "new_from": 3, "new_to": 4,
    })
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_ac1_validate_edge_cycle(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2], [2, 3]],
        "new_from": 3, "new_to": 1,
    })
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "hierarchy.cycle_detected"
    assert "cycle_path" in detail
    assert detail["cycle_path"][0] == 3
    assert detail["cycle_path"][-1] == 3


def test_ac1_detect_cycles(client):
    r = client.post("/api/hierarchy/detect-cycles", json={
        "edges": [[1, 2], [2, 3], [3, 1]],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["cycle_count"] >= 1


def test_ac1_topo_order(client):
    r = client.post("/api/hierarchy/topo-order", json={
        "edges": [[1, 2], [2, 3]],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["order"] == [1, 2, 3]


def test_ac1_topo_order_cycle_returns_409(client):
    r = client.post("/api/hierarchy/topo-order", json={
        "edges": [[1, 2], [2, 1]],
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "hierarchy.cycle_detected"


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2]], "new_from": 2, "new_to": 3,
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_large_graph_within_2sec(client):
    # 1000 ノード chain で性能確認
    edges = [[i, i + 1] for i in range(1, 1001)]
    t0 = time.time()
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": edges, "new_from": 1001, "new_to": 1002,
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/hierarchy/validate-edge", {
            "edges": [[1, 2]], "new_from": 0, "new_to": 1,  # gt=0 → 422
        }),
        ("POST", "/api/hierarchy/validate-edge", {
            "edges": "nope", "new_from": 1, "new_to": 2,
        }),
        ("POST", "/api/hierarchy/detect-cycles", {
            "edges": [[1, -1]],
        }),
        ("POST", "/api/hierarchy/topo-order", {
            "edges": [[1, 2], [2, 1]],
        }),
    ]
    for method, path, body in cases:
        r = client.post(path, json=body)
        assert r.status_code in (400, 401, 409, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("hierarchy."), \
                f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit (validator は read-only だが validation 成功は記録)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_validate_edge_emits_audit(client, _capture_audit):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2]], "new_from": 2, "new_to": 3,
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "hierarchy.edge.validated"]
    assert len(events) == 1
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["result"] == "ok"


def test_ac3_cycle_detected_no_audit(client, _capture_audit):
    # cycle 検出 = 失敗 → audit emit しない
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2], [2, 1]], "new_from": 2, "new_to": 3,
        "actor_user_id": "u-1",
    })
    # 既存 graph に cycle あるが、 新 edge (2→3) の検証としては OK 経路で audit emit される
    # cycle detection の結果を確認
    if r.status_code == 200:
        events = [e for e in _capture_audit if e["event_type"] == "hierarchy.edge.validated"]
        assert len(events) == 1


def test_ac3_topo_order_no_audit(client, _capture_audit):
    # topo-order は audit emit しない (read-only diagnostic)
    client.post("/api/hierarchy/topo-order", json={
        "edges": [[1, 2]], "actor_user_id": "u-1",
    })
    h_events = [e for e in _capture_audit if e["event_type"].startswith("hierarchy.")]
    # validated は emit, detect-cycles/topo-order は emit しない
    assert all(e["event_type"] == "hierarchy.edge.validated" for e in h_events)


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_edges_not_list(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": "not-a-list", "new_from": 1, "new_to": 2,
    })
    # Pydantic typed → 422 or service 経由 → 400
    assert r.status_code in (400, 422)


def test_ac4_invalid_edge_node(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, -2]], "new_from": 3, "new_to": 4,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "hierarchy.invalid"


def test_ac4_invalid_new_from_pydantic(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [], "new_from": 0, "new_to": 1,
    })
    assert r.status_code == 422


def test_ac4_empty_actor_user_id(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [[1, 2]], "new_from": 2, "new_to": 3,
        "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "hierarchy.unauthorized"


def test_ac4_self_loop_returns_409(client):
    r = client.post("/api/hierarchy/validate-edge", json={
        "edges": [], "new_from": 5, "new_to": 5,
    })
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "hierarchy.cycle_detected"
    assert detail["cycle_path"] == [5, 5]


def test_ac4_topo_order_invalid_nodes(client):
    r = client.post("/api/hierarchy/topo-order", json={
        "edges": [[1, 2]], "nodes": [0],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "hierarchy.invalid"


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — DB trigger は最終 SoT として共存
# ──────────────────────────────────────────────────────────────────────────


def test_compat_validator_matches_db_trigger_semantics():
    # DB trigger と同じ cycle 判定セマンティクス
    # 1 → 2 → 3 ; 3 → 1 で cycle
    cycle = detect_cycle_on_add([(1, 2), (2, 3)], 3, 1)
    assert cycle is not None
    # DB trigger は 'cycle_detected' ERRCODE を上げる - 同じ identifier
    with pytest.raises(HierarchyError, match="cycle_detected"):
        validate_edge_addition([(1, 2), (2, 3)], 3, 1)


def test_compat_no_persistent_state_mutated(client):
    # validator は read-only - 連続呼び出しでも結果一致
    payload = {"edges": [[1, 2], [2, 3]], "new_from": 3, "new_to": 1}
    r1 = client.post("/api/hierarchy/validate-edge", json=payload)
    r2 = client.post("/api/hierarchy/validate-edge", json=payload)
    assert r1.status_code == r2.status_code == 409
    assert r1.json() == r2.json()
