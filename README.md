# Mini Git

커밋 메타데이터를 메모리에 기록하며 그래프, 탐색, 역색인, 정렬의 핵심 원리를 학습하는 Python 3.10+ CLI 프로그램입니다. 파일 내용 추적, 네트워크 통신, 영속 저장, 선택 과제(Diff/Merge)는 포함하지 않습니다.

## 실행

```bash
python3 main.py
```

프롬프트에서 명령을 반복 입력하고 `exit` 또는 `quit`로 종료합니다. 명령어는 대소문자를 구분하지 않으며 공백을 포함하는 문자열은 따옴표로 감쌉니다.

```text
mini-git> INIT "Alice Kim"
Initialized repository.
Current branch: main
Current user: Alice Kim
mini-git> COMMIT "Initial commit"
[main c000001] Initial commit
mini-git> BRANCH feature
Created branch: feature
mini-git> SWITCH feature
Switched to branch: feature
mini-git> COMMIT "Add login feature"
[feature c000002] Add login feature
mini-git> LOG
mini-git> PATH c000001 c000002
Path: c000001 -> c000002
mini-git> SEARCH login
mini-git> SEARCH --author="Alice Kim"
mini-git> ANCESTORS c000002
mini-git> LOG --sort-by=date
mini-git> LOG --sort-by=author
mini-git> quit
```

## 명령

| 명령 | 동작 |
|---|---|
| `INIT <user_name>` | 저장소를 초기화하고 `main`, HEAD, 현재 사용자를 설정 |
| `BRANCH <branch_name>` | 현재 커밋을 가리키는 브랜치 생성 |
| `SWITCH <branch_name>` | HEAD를 해당 브랜치로 이동 |
| `COMMIT <message>` | 현재 HEAD를 부모로 하는 커밋 생성 및 역색인 갱신 |
| `LOG` | 부모가 자식보다 먼저 나오도록 전체 커밋 출력 |
| `LOG --sort-by=date\|author` | 직접 구현한 안정 병합 정렬로 전체 커밋 정렬 |
| `PATH <commit1> <commit2>` | 부모 연결을 무방향 간선으로 본 최단 경로 출력 |
| `ANCESTORS <hash>` | 도달 가능한 모든 조상 출력 |
| `SEARCH <keyword>` | keyword 역색인으로 검색 |
| `SEARCH --author=<name>` | author 역색인으로 검색 |

## 설계 요약

- `Commit`은 `hash`, `message`, `author`, `timestamp`, `parents`를 가진 불변 노드입니다.
- `commits` 해시맵은 hash에서 커밋으로 평균 O(1) 조회를 제공합니다.
- `branches`는 브랜치 이름에서 HEAD 커밋 hash로 연결되며, 현재 브랜치가 HEAD 역할을 합니다.
- 커밋은 이미 존재하는 현재 HEAD만 부모로 삼으므로 그래프는 DAG로 유지됩니다.
- `LOG`는 Kahn 방식의 위상 정렬, `PATH`는 BFS, `ANCESTORS`는 DFS 계열 순회를 사용합니다.
- keyword/author 역색인은 커밋 생성 시 갱신됩니다. 메시지 토큰은 `split()` 후 소문자로 정규화합니다.
- 날짜/작성자 정렬에는 표준 정렬 API 대신 직접 구현한 안정 병합 정렬을 사용합니다.
- hash는 세션 내 단조 증가 카운터(`c000001` 등)로 생성해 충돌을 방지합니다.

## 테스트

```bash
python3 -m unittest -v
```

테스트는 초기화, 브랜치/HEAD, 부모 우선 로그, 경로와 단절 그래프, 조상, 역색인, 안정 정렬, CLI 문법과 REPL 종료를 검증합니다.

## 개념서

실제 Git/GitHub의 staging과 object 흐름부터 `main.py` 코드 리뷰, 위상 정렬, BFS/DFS, 안정 병합 정렬, 역색인 및 평가 질문 답변까지 정리한 문서는 [`output/pdf/mini_git_concept_guide_ko.pdf`](output/pdf/mini_git_concept_guide_ko.pdf)에서 확인할 수 있습니다.
