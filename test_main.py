"""Requirement-focused tests for the Mini Git implementation."""

import io
import unittest
from datetime import datetime, timedelta

from main import MiniGitRepository, execute_command, merge_sort, run_repl


class StepClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, 9, 0, 0)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(minutes=1)
        return current


class MiniGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MiniGitRepository(clock=StepClock())
        self.repo.initialize("Alice")

    def test_init_sets_main_head_and_user(self) -> None:
        self.assertEqual(self.repo.current_branch, "main")
        self.assertEqual(self.repo.current_user, "Alice")
        self.assertIsNone(self.repo.branches["main"])

    def test_branch_switch_and_commit_update_selected_branch(self) -> None:
        first = self.repo.create_commit("Initial commit")
        self.repo.create_branch("feature")
        self.repo.switch("feature")
        second = self.repo.create_commit("Add login")
        self.assertEqual(second.parents, (first.hash,))
        self.assertEqual(self.repo.branches["feature"], second.hash)
        self.assertEqual(self.repo.branches["main"], first.hash)

    def test_log_places_parent_before_children(self) -> None:
        root = self.repo.create_commit("root")
        self.repo.create_branch("feature")
        main_child = self.repo.create_commit("main child")
        self.repo.switch("feature")
        feature_child = self.repo.create_commit("feature child")
        hashes = [commit.hash for commit in self.repo.topological_commits()]
        self.assertEqual(hashes[0], root.hash)
        self.assertLess(hashes.index(root.hash), hashes.index(main_child.hash))
        self.assertLess(hashes.index(root.hash), hashes.index(feature_child.hash))

    def test_path_is_shortest_and_disconnected_graph_has_no_path(self) -> None:
        self.repo.create_branch("other-root")
        first = self.repo.create_commit("main root")
        second = self.repo.create_commit("main child")
        self.assertEqual(self.repo.shortest_path(first.hash, second.hash), [first.hash, second.hash])
        self.repo.switch("other-root")
        isolated = self.repo.create_commit("isolated root")
        self.assertIsNone(self.repo.shortest_path(second.hash, isolated.hash))

    def test_ancestors_returns_every_parent_without_self(self) -> None:
        first = self.repo.create_commit("one")
        second = self.repo.create_commit("two")
        third = self.repo.create_commit("three")
        self.assertEqual(
            [commit.hash for commit in self.repo.ancestors(third.hash)],
            [first.hash, second.hash],
        )

    def test_indexes_are_updated_at_commit_time(self) -> None:
        commit = self.repo.create_commit("Add Login login")
        self.assertEqual(self.repo.keyword_index["login"], [commit.hash])
        self.assertEqual(self.repo.author_index["alice"], [commit.hash])
        self.assertEqual(self.repo.search_keyword("LOGIN"), [commit])
        self.assertEqual(self.repo.search_author("alice"), [commit])

    def test_custom_merge_sort_is_stable(self) -> None:
        values = [("b", 1), ("a", 2), ("a", 3)]
        self.assertEqual(merge_sort(values, key=lambda item: item[0]), [("a", 2), ("a", 3), ("b", 1)])

    def test_command_parser_supports_quotes_case_and_errors(self) -> None:
        repo = MiniGitRepository(clock=StepClock())
        self.assertIn("Current user: Alice Smith", execute_command(repo, 'init "Alice Smith"'))
        result = execute_command(repo, 'CoMmIt "Add login feature"')
        self.assertIn("Add login feature", result)
        self.assertEqual(execute_command(repo, "switch missing"), "Unknown branch: missing")
        self.assertEqual(execute_command(repo, "commit too many words"), "Invalid args")

    def test_repl_repeats_until_quit(self) -> None:
        source = io.StringIO('init Alice\ncommit "Initial commit"\nquit\n')
        output = io.StringIO()
        run_repl(source, output)
        transcript = output.getvalue()
        self.assertEqual(transcript.count("mini-git> "), 3)
        self.assertIn("Initialized repository.", transcript)
        self.assertIn("Initial commit", transcript)


if __name__ == "__main__":
    unittest.main()
