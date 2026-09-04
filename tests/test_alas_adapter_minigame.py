"""Minigame ticket-contract regression cases for the adapter."""

import unittest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed


class TicketOracle:
    def __init__(self, selected, owned):
        self.value = (selected, owned)

    def new_year_challenge_ticket_count(self):
        return self.value


class AlasSemanticAdapterMinigameTests(unittest.TestCase):
    def make_adapter(self, selected=1, owned=20):
        oracle = TicketOracle(selected, owned)
        adapter = AlasSemanticAdapter(
            oracle,
            lambda: None,
            minigame_play_budget=1,
        )
        adapter.begin_minigame()
        adapter._minigame_context.coins_owned = owned
        return adapter, oracle

    def test_default_ticket_uses_selected_and_owned_counter_contract(self):
        adapter, _ = self.make_adapter(selected=1, owned=7)

        self.assertEqual(adapter.minigame_prepare_default_ticket(), 1)
        self.assertEqual(adapter._minigame_context.selected_tickets, 1)

    def test_default_ticket_rejects_more_than_one_selected_ticket(self):
        adapter, _ = self.make_adapter(selected=2, owned=20)

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            adapter.minigame_prepare_default_ticket()

    def test_default_ticket_rejects_counter_inventory_mismatch(self):
        adapter, oracle = self.make_adapter(selected=1, owned=20)
        oracle.value = (1, 19)

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            adapter.minigame_prepare_default_ticket()


if __name__ == "__main__":
    unittest.main()
