"""Tests for data_processing module: de-duplication and grouping logic."""

import unittest

from data_processing import group_entries_by_game, process_entries


class TestProcessEntries(unittest.TestCase):

    def test_excludes_entries_without_any_identifier(self):
        entries = [
            {"badge_id": "B1", "librarygame_id": "G1"},
            {"badge_id": None, "librarygame_id": "G1"},
            {"badge_id": "", "librarygame_id": "G1"},
            {"librarygame_id": "G1"},  # missing all identifiers
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["badge_id"], "B1")

    def test_deduplicates_by_badge_and_game(self):
        entries = [
            {"badge_id": "B1", "librarygame_id": "G1", "id": "e1"},
            {"badge_id": "B1", "librarygame_id": "G1", "id": "e2"},  # dup
            {"badge_id": "B1", "librarygame_id": "G2", "id": "e3"},  # different game
            {"badge_id": "B2", "librarygame_id": "G1", "id": "e4"},  # different badge
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 3)
        ids = [e["id"] for e in result]
        self.assertIn("e1", ids)
        self.assertNotIn("e2", ids)  # duplicate dropped
        self.assertIn("e3", ids)
        self.assertIn("e4", ids)

    def test_keeps_first_occurrence_on_duplicate(self):
        entries = [
            {"badge_id": "B1", "librarygame_id": "G1", "id": "first"},
            {"badge_id": "B1", "librarygame_id": "G1", "id": "second"},
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "first")

    def test_empty_input(self):
        self.assertEqual(process_entries([]), [])

    def test_all_entries_missing_all_identifiers(self):
        entries = [
            {"badge_id": None, "librarygame_id": "G1"},
            {"badge_id": "", "librarygame_id": "G2"},
        ]
        self.assertEqual(process_entries(entries), [])

    def test_falls_back_to_user_id_when_no_badge(self):
        entries = [
            {"user_id": "U1", "librarygame_id": "G1", "name": "Alice"},
            {"user_id": "U2", "librarygame_id": "G1", "name": "Bob"},
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 2)
        # badge_id should be normalized to user_id
        self.assertEqual(result[0]["badge_id"], "U1")
        self.assertEqual(result[1]["badge_id"], "U2")

    def test_user_id_fallback_deduplicates(self):
        entries = [
            {"user_id": "U1", "librarygame_id": "G1", "id": "e1"},
            {"user_id": "U1", "librarygame_id": "G1", "id": "e2"},
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "e1")

    def test_badge_id_takes_precedence_over_user_id(self):
        entries = [
            {"badge_id": "B1", "user_id": "U1", "librarygame_id": "G1"},
        ]
        result = process_entries(entries)
        self.assertEqual(result[0]["badge_id"], "B1")

    def test_falls_back_to_name_when_no_badge_or_user(self):
        entries = [
            {"name": "Abc", "librarygame_id": "G1"},
            {"name": "Def", "librarygame_id": "G1"},
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["badge_id"], "Abc")
        self.assertEqual(result[1]["badge_id"], "Def")

    def test_name_fallback_deduplicates(self):
        entries = [
            {"name": "Abc", "librarygame_id": "G1", "id": "e1"},
            {"name": "Abc", "librarygame_id": "G1", "id": "e2"},
        ]
        result = process_entries(entries)
        self.assertEqual(len(result), 1)


class TestGroupEntriesByGame(unittest.TestCase):

    def test_groups_entries_to_correct_game(self):
        games = [
            {"id": "G1", "name": "Game A"},
            {"id": "G2", "name": "Game B"},
        ]
        entries = [
            {"badge_id": "B1", "librarygame_id": "G1"},
            {"badge_id": "B2", "librarygame_id": "G1"},
            {"badge_id": "B3", "librarygame_id": "G2"},
        ]
        result = group_entries_by_game(entries, games)
        self.assertEqual(len(result), 2)

        g1 = next(g for g in result if g["game"]["id"] == "G1")
        g2 = next(g for g in result if g["game"]["id"] == "G2")

        self.assertEqual(g1["entrant_count"], 2)
        self.assertEqual(g2["entrant_count"], 1)

    def test_game_with_zero_entries(self):
        games = [
            {"id": "G1", "name": "Game A"},
            {"id": "G2", "name": "Game B"},
        ]
        entries = [
            {"badge_id": "B1", "librarygame_id": "G1"},
        ]
        result = group_entries_by_game(entries, games)
        g2 = next(g for g in result if g["game"]["id"] == "G2")
        self.assertEqual(g2["entrant_count"], 0)
        self.assertEqual(g2["entries"], [])

    def test_empty_games_and_entries(self):
        result = group_entries_by_game([], [])
        self.assertEqual(result, [])

    def test_no_games_with_entries(self):
        entries = [{"badge_id": "B1", "librarygame_id": "G1"}]
        result = group_entries_by_game(entries, [])
        self.assertEqual(result, [])

    def test_preserves_game_metadata(self):
        games = [{"id": "G1", "name": "Catan", "publisher_name": "Kosmos"}]
        entries = [{"badge_id": "B1", "librarygame_id": "G1"}]
        result = group_entries_by_game(entries, games)
        self.assertEqual(result[0]["game"]["publisher_name"], "Kosmos")


if __name__ == "__main__":
    unittest.main()
