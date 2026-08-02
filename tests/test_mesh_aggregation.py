# -*- encoding: utf-8 -*-
"""Tests de l'agrégation des résultats entre pairs (aggregation.py)."""
import pytest

from sphinxcontrib.osint.mesh.aggregation import aggregate_results, normalize_peer_scores


# -- normalize_peer_scores : minmax ---------------------------------------

def test_minmax_best_and_worst_map_to_1_and_0():
    results = [{'id': 'a', 'score': 10.0}, {'id': 'b', 'score': 5.0}, {'id': 'c', 'score': 0.0}]

    normalized = normalize_peer_scores(results, method='minmax')

    by_id = {r['id']: r['normalized_score'] for r in normalized}
    assert by_id['a'] == pytest.approx(1.0)
    assert by_id['c'] == pytest.approx(0.0)
    assert by_id['b'] == pytest.approx(0.5)


def test_minmax_single_result_gets_full_score():
    results = [{'id': 'a', 'score': 3.7}]

    normalized = normalize_peer_scores(results, method='minmax')

    assert normalized[0]['normalized_score'] == 1.0


def test_minmax_all_equal_scores_get_full_score():
    # évite une division par zéro (span == 0) et évite de tout ramener à
    # 0, ce qui ferait perdre injustement ce lot face à d'autres pairs.
    results = [{'id': 'a', 'score': 5.0}, {'id': 'b', 'score': 5.0}]

    normalized = normalize_peer_scores(results, method='minmax')

    assert all(r['normalized_score'] == 1.0 for r in normalized)


def test_minmax_missing_score_treated_as_zero():
    results = [{'id': 'a', 'score': 10.0}, {'id': 'b'}]  # pas de clé 'score'

    normalized = normalize_peer_scores(results, method='minmax')

    by_id = {r['id']: r['normalized_score'] for r in normalized}
    assert by_id['b'] == 0.0


# -- normalize_peer_scores : rank ------------------------------------------

def test_rank_orders_regardless_of_score_gap():
    # deux résultats très proches en score et un loin derrière -- le
    # classement par rang ignore l'écart, contrairement à minmax.
    results = [{'id': 'a', 'score': 9.99}, {'id': 'b', 'score': 9.98}, {'id': 'c', 'score': 0.01}]

    normalized = normalize_peer_scores(results, method='rank')

    by_id = {r['id']: r['normalized_score'] for r in normalized}
    assert by_id['a'] == pytest.approx(1.0)
    assert by_id['c'] == pytest.approx(0.0)
    assert by_id['b'] == pytest.approx(0.5)


def test_rank_does_not_assume_input_already_sorted():
    # volontairement dans le désordre
    results = [{'id': 'low', 'score': 1.0}, {'id': 'high', 'score': 9.0}, {'id': 'mid', 'score': 5.0}]

    normalized = normalize_peer_scores(results, method='rank')

    by_id = {r['id']: r['normalized_score'] for r in normalized}
    assert by_id['high'] > by_id['mid'] > by_id['low']


def test_rank_single_result_gets_full_score():
    assert normalize_peer_scores([{'id': 'a', 'score': 1.0}], method='rank')[0]['normalized_score'] == 1.0


# -- erreurs / cas limites --------------------------------------------------

def test_empty_results_returns_empty_list():
    assert normalize_peer_scores([], method='minmax') == []


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        normalize_peer_scores([{'id': 'a', 'score': 1.0}], method='does-not-exist')


def test_normalize_does_not_mutate_input():
    original = [{'id': 'a', 'score': 1.0}]
    normalize_peer_scores(original, method='minmax')
    assert 'normalized_score' not in original[0]


# -- aggregate_results -------------------------------------------------------

def test_aggregate_merges_and_sorts_across_peers():
    results_by_peer = {
        'osint-fr': [{'id': 'fr-1', 'score': 10.0}, {'id': 'fr-2', 'score': 2.0}],
        'osint-de': [{'id': 'de-1', 'score': 100.0}],  # échelle de score totalement différente
    }

    merged = aggregate_results(results_by_peer)

    # de-1 est le seul résultat de son pair -> normalized_score = 1.0,
    # ex-aequo avec fr-1 (meilleur résultat de osint-fr) -- ce qui est
    # justement le but: comparer les positions relatives, pas les scores bruts.
    ids_ranked = [r['id'] for r in merged]
    assert ids_ranked.index('fr-2') > ids_ranked.index('fr-1')
    assert ids_ranked.index('fr-2') > ids_ranked.index('de-1')


def test_aggregate_tags_each_result_with_its_peer_id():
    results_by_peer = {'osint-fr': [{'id': 'fr-1', 'score': 1.0}]}

    merged = aggregate_results(results_by_peer)

    assert merged[0]['peer_id'] == 'osint-fr'


def test_aggregate_respects_limit():
    results_by_peer = {
        'osint-fr': [{'id': f'fr-{i}', 'score': float(i)} for i in range(5)],
    }

    merged = aggregate_results(results_by_peer, limit=2)

    assert len(merged) == 2
    assert merged[0]['id'] == 'fr-4'  # le meilleur score d'abord


def test_aggregate_skips_peers_with_no_results():
    results_by_peer = {'osint-fr': [{'id': 'fr-1', 'score': 1.0}], 'osint-down': []}

    merged = aggregate_results(results_by_peer)

    assert [r['id'] for r in merged] == ['fr-1']


def test_aggregate_with_rank_method():
    results_by_peer = {
        'osint-fr': [{'id': 'fr-1', 'score': 9.0}, {'id': 'fr-2', 'score': 1.0}],
        'osint-de': [{'id': 'de-1', 'score': 500.0}, {'id': 'de-2', 'score': 499.0}],
    }

    merged = aggregate_results(results_by_peer, method='rank')

    # meilleur de chaque pair en tête, ex-aequo (normalized_score=1.0 chacun)
    top_ids = {merged[0]['id'], merged[1]['id']}
    assert top_ids == {'fr-1', 'de-1'}
