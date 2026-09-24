"""In-memory Mini Git for studying graphs, indexes, and sorting."""

from __future__ import annotations

import shlex
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, TextIO, TypeVar


T = TypeVar("T")


class MiniGitError(Exception):
    """A user-facing repository or command error."""


@dataclass(frozen=True)
class Commit:
    """An immutable node in the commit DAG."""

    hash: str
    message: str
    author: str
    timestamp: datetime
    parents: tuple[str, ...]


def merge_sort(items: Iterable[T], key: Callable[[T], object]) -> list[T]:
    """Return a stable merge sort without using standard sorting APIs."""

    values = list(items)
    if len(values) < 2:
        return values

    middle = len(values) // 2
    left = merge_sort(values[:middle], key)
    right = merge_sort(values[middle:], key)
    result: list[T] = []
    left_index = right_index = 0

    while left_index < len(left) and right_index < len(right):
        if key(left[left_index]) <= key(right[right_index]):
            result.append(left[left_index])
            left_index += 1
        else:
            result.append(right[right_index])
            right_index += 1

    return result + left[left_index:] + right[right_index:]


class MiniGitRepository:
    """Manage commits, branches, indexes, and graph queries."""

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
        """Reset the repository and create the main branch."""

        if not user_name.strip():
            raise MiniGitError("Invalid args")
        self.initialized = True
        self.current_user = user_name
        self.current_branch = "main"
        self.commits = {}
        self.branches = {"main": None}
        self.keyword_index = {}
        self.author_index = {}
        self._commit_order = {}
        self._next_hash = 1

    def create_branch(self, branch_name: str) -> None:
        """Create a branch at the current HEAD."""

        self._require_initialized()
        if not branch_name.strip():
            raise MiniGitError("Invalid args")
        if branch_name in self.branches:
            raise MiniGitError(f"Branch already exists: {branch_name}")
        self.branches[branch_name] = self.branches[self.current_branch]

    def switch(self, branch_name: str) -> None:
        """Move HEAD to an existing branch."""

        self._require_initialized()
        if branch_name not in self.branches:
            raise MiniGitError(f"Unknown branch: {branch_name}")
        self.current_branch = branch_name

    def create_commit(self, message: str) -> Commit:
        """Create a commit at HEAD and update its search indexes."""

        self._require_initialized()
        if not message.strip():
            raise MiniGitError("Invalid args")

        head = self.branches[self.current_branch]
        commit = Commit(
            hash=self._new_hash(),
            message=message,
            author=self.current_user,
            timestamp=self._clock(),
            parents=() if head is None else (head,),
        )
        self.commits[commit.hash] = commit
        self._commit_order[commit.hash] = len(self._commit_order)
        self.branches[self.current_branch] = commit.hash
        self._index_commit(commit)
        return commit

    def topological_commits(self) -> list[Commit]:
        """Return all commits with every parent before its children."""

        self._require_initialized()
        children = {commit_hash: [] for commit_hash in self.commits}
        remaining = {
            commit.hash: len(commit.parents)
            for commit in self.commits.values()
        }
        for commit in self.commits.values():
            for parent in commit.parents:
                children[parent].append(commit.hash)

        ready = deque(commit_hash for commit_hash, count in remaining.items() if count == 0)
        result: list[Commit] = []
        while ready:
            commit_hash = ready.popleft()
            result.append(self.commits[commit_hash])
            for child in children[commit_hash]:
                remaining[child] -= 1
                if remaining[child] == 0:
                    ready.append(child)

        if len(result) != len(self.commits):
            raise RuntimeError("Commit graph contains a cycle")
        return result

    def sorted_commits(self, criterion: str) -> list[Commit]:
        """Sort commits by date or author with the custom merge sort."""

        commits = self.topological_commits()
        if criterion == "date":
            return merge_sort(commits, lambda commit: commit.timestamp)
        if criterion == "author":
            return merge_sort(commits, lambda commit: commit.author.casefold())
        raise MiniGitError("Invalid args")

    def shortest_path(self, start: str, end: str) -> list[str] | None:
        """Return the lexicographically smallest undirected shortest path."""

        self._require_commit(start)
        self._require_commit(end)
        if start == end:
            return [start]

        neighbors = {commit_hash: [] for commit_hash in self.commits}
        for commit in self.commits.values():
            for parent in commit.parents:
                neighbors[commit.hash].append(parent)
                neighbors[parent].append(commit.hash)
        for commit_hash in neighbors:
            neighbors[commit_hash] = merge_sort(neighbors[commit_hash], lambda value: value)

        queue = deque([start])
        previous: dict[str, str | None] = {start: None}
        while queue:
            current = queue.popleft()
            for neighbor in neighbors[current]:
                if neighbor in previous:
                    continue
                previous[neighbor] = current
                if neighbor == end:
                    path = [end]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbor)
        return None

    def ancestors(self, commit_hash: str) -> list[Commit]:
        """Return every reachable parent in parent-first order."""

        self._require_commit(commit_hash)
        found: set[str] = set()
        stack = list(self.commits[commit_hash].parents)
        while stack:
            ancestor = stack.pop()
            if ancestor not in found:
                found.add(ancestor)
                stack.extend(self.commits[ancestor].parents)
        return [commit for commit in self.topological_commits() if commit.hash in found]

    def search_keyword(self, keyword: str) -> list[Commit]:
        """Find commits containing every normalized query token."""

        self._require_initialized()
        tokens = keyword.lower().split()
        if not tokens:
            raise MiniGitError("Invalid args")
        matches = set(self.keyword_index.get(tokens[0], []))
        for token in tokens[1:]:
            matches &= set(self.keyword_index.get(token, []))
        return self._ordered_commits(matches)

    def search_author(self, author: str) -> list[Commit]:
        """Find commits through the normalized author index."""

        self._require_initialized()
        if not author.strip():
            raise MiniGitError("Invalid args")
        return self._ordered_commits(set(self.author_index.get(author.casefold(), [])))

    def _ordered_commits(self, hashes: set[str]) -> list[Commit]:
        commits = [self.commits[commit_hash] for commit_hash in hashes]
        return merge_sort(commits, lambda commit: self._commit_order[commit.hash])

    def _new_hash(self) -> str:
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
    """Format one commit for CLI output."""

    return (
        f"commit {commit.hash} "
        f"({commit.author}, {commit.timestamp:%Y-%m-%d %H:%M:%S})\n"
        f"  {commit.message}"
    )


def format_commits(commits: list[Commit]) -> str:
    """Format a list of commits for CLI output."""

    if not commits:
        return "No commits"
    return "\n".join(format_commit(commit) for commit in commits)


def _require_args(args: list[str], count: int) -> None:
    if len(args) != count:
        raise MiniGitError("Invalid args")


def execute_command(repository: MiniGitRepository, line: str) -> str | None:
    """Parse and execute one case-insensitive REPL command."""

    try:
        parts = shlex.split(line)
    except ValueError:
        return "Invalid args"
    if not parts:
        return None

    command, args = parts[0].upper(), parts[1:]
    try:
        if command in {"EXIT", "QUIT"}:
            _require_args(args, 0)
            return "__EXIT__"
        if command == "INIT":
            _require_args(args, 1)
            repository.initialize(args[0])
            return (
                "Initialized repository.\n"
                f"Current branch: {repository.current_branch}\n"
                f"Current user: {repository.current_user}"
            )
        if command == "BRANCH":
            _require_args(args, 1)
            repository.create_branch(args[0])
            return f"Created branch: {args[0]}"
        if command == "SWITCH":
            _require_args(args, 1)
            repository.switch(args[0])
            return f"Switched to branch: {args[0]}"
        if command == "COMMIT":
            _require_args(args, 1)
            commit = repository.create_commit(args[0])
            return f"[{repository.current_branch} {commit.hash}] {commit.message}"
        if command == "LOG":
            if not args:
                return format_commits(repository.topological_commits())
            _require_args(args, 1)
            option, separator, criterion = args[0].partition("=")
            if option.lower() != "--sort-by" or not separator:
                raise MiniGitError("Invalid args")
            return format_commits(repository.sorted_commits(criterion.lower()))
        if command == "PATH":
            _require_args(args, 2)
            path = repository.shortest_path(*args)
            return "No path" if path is None else "Path: " + " -> ".join(path)
        if command == "ANCESTORS":
            _require_args(args, 1)
            return format_commits(repository.ancestors(args[0]))
        if command == "SEARCH":
            _require_args(args, 1)
            option, separator, author = args[0].partition("=")
            if separator and option.lower() == "--author":
                return format_commits(repository.search_author(author))
            return format_commits(repository.search_keyword(args[0]))
        return f"Unknown command: {parts[0]}"
    except MiniGitError as error:
        return str(error)


def run_repl(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
    """Read and execute commands until EOF, EXIT, or QUIT."""

    repository = MiniGitRepository()
    while True:
        output_stream.write("mini-git> ")
        output_stream.flush()
        line = input_stream.readline()
        if not line:
            output_stream.write("\n")
            return
        result = execute_command(repository, line)
        if result == "__EXIT__":
            return
        if result is not None:
            output_stream.write(result + "\n")


if __name__ == "__main__":
    run_repl()
