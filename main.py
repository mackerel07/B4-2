"""A small, in-memory Git model used to study graphs, indexes, and sorting."""

from __future__ import annotations

import shlex
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, TextIO, TypeVar


T = TypeVar("T")


class MiniGitError(Exception):
    """An expected command or repository error that is safe to show to users."""


@dataclass(frozen=True)
class Commit:
    """One immutable commit node in the directed acyclic commit graph."""

    hash: str
    message: str
    author: str
    timestamp: datetime
    parents: tuple[str, ...]


def merge_sort(items: Iterable[T], key: Callable[[T], object]) -> list[T]:
    """Return a stable O(n log n) merge sort without standard sorting APIs."""

    values = list(items)
    if len(values) < 2:
        return values

    middle = len(values) // 2
    left = merge_sort(values[:middle], key)
    right = merge_sort(values[middle:], key)
    merged: list[T] = []
    left_index = 0
    right_index = 0

    while left_index < len(left) and right_index < len(right):
        # Choosing the left item on equal keys is what makes this sort stable.
        if key(left[left_index]) <= key(right[right_index]):
            merged.append(left[left_index])
            left_index += 1
        else:
            merged.append(right[right_index])
            right_index += 1

    merged.extend(left[left_index:])
    merged.extend(right[right_index:])
    return merged


class MiniGitRepository:
    """Own repository state and provide graph, branch, index, and query operations."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or datetime.now
        self.initialized = False
        self.current_user = ""
        self.current_branch = ""
        self.commits: dict[str, Commit] = {}
        self.branches: dict[str, str | None] = {}
        self.keyword_index: dict[str, list[str]] = {}
        self.author_index: dict[str, list[str]] = {}
        self._commit_order: dict[str, int] = {}
        self._next_hash = 1

    def initialize(self, user_name: str) -> None:
        """Reset all in-memory state and create an empty main branch."""

        if not user_name.strip():
            raise MiniGitError("Invalid args")
        self.initialized = True
        self.current_user = user_name
        self.current_branch = "main"
        self.commits.clear()
        self.branches = {"main": None}
        self.keyword_index.clear()
        self.author_index.clear()
        self._commit_order.clear()
        self._next_hash = 1

    def create_branch(self, branch_name: str) -> None:
        """Create a branch pointing at the current branch head."""

        self._require_initialized()
        if not branch_name.strip():
            raise MiniGitError("Invalid args")
        if branch_name in self.branches:
            raise MiniGitError(f"Branch already exists: {branch_name}")
        self.branches[branch_name] = self.branches[self.current_branch]

    def switch(self, branch_name: str) -> None:
        """Move HEAD by selecting an existing branch."""

        self._require_initialized()
        if branch_name not in self.branches:
            raise MiniGitError(f"Unknown branch: {branch_name}")
        self.current_branch = branch_name

    def create_commit(self, message: str) -> Commit:
        """Append a commit to HEAD and update both inverted indexes immediately."""

        self._require_initialized()
        if not message.strip():
            raise MiniGitError("Invalid args")

        parent = self.branches[self.current_branch]
        parents = () if parent is None else (parent,)
        commit_hash = self._new_hash()
        commit = Commit(
            hash=commit_hash,
            message=message,
            author=self.current_user,
            timestamp=self._clock(),
            parents=parents,
        )
        self.commits[commit_hash] = commit
        self._commit_order[commit_hash] = len(self._commit_order)
        self.branches[self.current_branch] = commit_hash
        self._index_commit(commit)
        return commit

    def topological_commits(self) -> list[Commit]:
        """Return every commit with all parents placed before their children."""

        self._require_initialized()
        children: dict[str, list[str]] = {commit_hash: [] for commit_hash in self.commits}
        remaining_parents: dict[str, int] = {}

        for commit in self.commits.values():
            remaining_parents[commit.hash] = len(commit.parents)
            for parent_hash in commit.parents:
                children[parent_hash].append(commit.hash)

        ready = deque(
            commit_hash
            for commit_hash, count in remaining_parents.items()
            if count == 0
        )
        output: list[Commit] = []
        while ready:
            commit_hash = ready.popleft()
            output.append(self.commits[commit_hash])
            for child_hash in children[commit_hash]:
                remaining_parents[child_hash] -= 1
                if remaining_parents[child_hash] == 0:
                    ready.append(child_hash)

        if len(output) != len(self.commits):
            raise RuntimeError("Commit graph contains a cycle")
        return output

    def sorted_commits(self, criterion: str) -> list[Commit]:
        """Sort all commits by date or author using the custom stable merge sort."""

        commits = self.topological_commits()
        if criterion == "date":
            return merge_sort(commits, key=lambda commit: commit.timestamp)
        if criterion == "author":
            return merge_sort(commits, key=lambda commit: commit.author.casefold())
        raise MiniGitError("Invalid args")

    def shortest_path(self, start_hash: str, end_hash: str) -> list[str] | None:
        """Find the lexicographically smallest shortest path using undirected BFS."""

        self._require_commit(start_hash)
        self._require_commit(end_hash)
        if start_hash == end_hash:
            return [start_hash]

        neighbors: dict[str, list[str]] = {commit_hash: [] for commit_hash in self.commits}
        for commit in self.commits.values():
            for parent_hash in commit.parents:
                neighbors[commit.hash].append(parent_hash)
                neighbors[parent_hash].append(commit.hash)

        for commit_hash, adjacent in neighbors.items():
            neighbors[commit_hash] = merge_sort(adjacent, key=lambda value: value)

        queue: deque[str] = deque([start_hash])
        visited = {start_hash}
        previous: dict[str, str | None] = {start_hash: None}
        while queue:
            current_hash = queue.popleft()
            for next_hash in neighbors[current_hash]:
                if next_hash in visited:
                    continue
                visited.add(next_hash)
                previous[next_hash] = current_hash
                if next_hash == end_hash:
                    path = [end_hash]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])
                    path.reverse()
                    return path
                queue.append(next_hash)
        return None

    def ancestors(self, commit_hash: str) -> list[Commit]:
        """Return all reachable parents, ordered so older ancestors appear first."""

        self._require_commit(commit_hash)
        found: set[str] = set()
        stack = list(self.commits[commit_hash].parents)
        while stack:
            ancestor_hash = stack.pop()
            if ancestor_hash in found:
                continue
            found.add(ancestor_hash)
            stack.extend(self.commits[ancestor_hash].parents)
        return [commit for commit in self.topological_commits() if commit.hash in found]

    def search_keyword(self, keyword: str) -> list[Commit]:
        """Use the token index to find commits containing every query token."""

        self._require_initialized()
        tokens = keyword.lower().split()
        if not tokens:
            raise MiniGitError("Invalid args")
        candidate_hashes: set[str] | None = None
        for token in tokens:
            token_hashes = set(self.keyword_index.get(token, []))
            candidate_hashes = (
                token_hashes
                if candidate_hashes is None
                else candidate_hashes & token_hashes
            )
        return self._ordered_candidates(candidate_hashes or set())

    def search_author(self, author: str) -> list[Commit]:
        """Use the normalized author index instead of scanning every commit."""

        self._require_initialized()
        if not author.strip():
            raise MiniGitError("Invalid args")
        return self._ordered_candidates(set(self.author_index.get(author.casefold(), [])))

    def _ordered_candidates(self, commit_hashes: set[str]) -> list[Commit]:
        candidates = [self.commits[commit_hash] for commit_hash in commit_hashes]
        return merge_sort(candidates, key=lambda commit: self._commit_order[commit.hash])

    def _new_hash(self) -> str:
        # A monotonic counter makes collisions impossible during one session.
        while True:
            candidate = f"c{self._next_hash:06x}"
            self._next_hash += 1
            if candidate not in self.commits:
                return candidate

    def _index_commit(self, commit: Commit) -> None:
        for token in set(commit.message.lower().split()):
            self.keyword_index.setdefault(token, []).append(commit.hash)
        self.author_index.setdefault(commit.author.casefold(), []).append(commit.hash)

    def _require_initialized(self) -> None:
        if not self.initialized:
            raise MiniGitError("Repository not initialized")

    def _require_commit(self, commit_hash: str) -> None:
        self._require_initialized()
        if commit_hash not in self.commits:
            raise MiniGitError(f"Unknown commit: {commit_hash}")


def format_commit(commit: Commit) -> str:
    """Format the fields required to identify a commit in command output."""

    timestamp = commit.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return f"commit {commit.hash} ({commit.author}, {timestamp})\n  {commit.message}"


def format_commits(commits: list[Commit]) -> str:
    """Format a commit list while keeping an empty result explicit."""

    if not commits:
        return "No commits"
    return "\n".join(format_commit(commit) for commit in commits)


def execute_command(repository: MiniGitRepository, line: str) -> str | None:
    """Parse and execute one case-insensitive REPL command."""

    try:
        parts = shlex.split(line)
    except ValueError:
        return "Invalid args"
    if not parts:
        return None

    command = parts[0].upper()
    args = parts[1:]
    try:
        if command in {"EXIT", "QUIT"}:
            if args:
                raise MiniGitError("Invalid args")
            return "__EXIT__"

        if command == "INIT":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            repository.initialize(args[0])
            return (
                "Initialized repository.\n"
                f"Current branch: {repository.current_branch}\n"
                f"Current user: {repository.current_user}"
            )

        if command == "BRANCH":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            repository.create_branch(args[0])
            return f"Created branch: {args[0]}"

        if command == "SWITCH":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            repository.switch(args[0])
            return f"Switched to branch: {args[0]}"

        if command == "COMMIT":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            commit = repository.create_commit(args[0])
            return f"[{repository.current_branch} {commit.hash}] {commit.message}"

        if command == "LOG":
            if not args:
                return format_commits(repository.topological_commits())
            if len(args) == 1 and args[0].lower().startswith("--sort-by="):
                criterion = args[0].split("=", 1)[1].lower()
                return format_commits(repository.sorted_commits(criterion))
            raise MiniGitError("Invalid args")

        if command == "PATH":
            if len(args) != 2:
                raise MiniGitError("Invalid args")
            path = repository.shortest_path(args[0], args[1])
            return "No path" if path is None else "Path: " + " -> ".join(path)

        if command == "ANCESTORS":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            return format_commits(repository.ancestors(args[0]))

        if command == "SEARCH":
            if len(args) != 1:
                raise MiniGitError("Invalid args")
            if args[0].lower().startswith("--author="):
                author = args[0].split("=", 1)[1]
                return format_commits(repository.search_author(author))
            return format_commits(repository.search_keyword(args[0]))

        return f"Unknown command: {parts[0]}"
    except MiniGitError as error:
        return str(error)


def run_repl(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> None:
    """Run the mini-git prompt until EOF, EXIT, or QUIT."""

    repository = MiniGitRepository()
    while True:
        output_stream.write("mini-git> ")
        output_stream.flush()
        line = input_stream.readline()
        if line == "":
            output_stream.write("\n")
            break
        result = execute_command(repository, line)
        if result == "__EXIT__":
            break
        if result is not None:
            output_stream.write(result + "\n")


if __name__ == "__main__":
    run_repl()
