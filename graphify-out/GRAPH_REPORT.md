# Graph Report - rusal-sanitizer  (2026-09-11)

## Corpus Check
- 1 files · ~4,088 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 28 nodes · 27 edges · 4 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a6edbc73`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Санитизация базы MySQL
- Роль языковой модели
- Как устроено решение
- Цикл автонастройки — как модель участвует в настройке

## God Nodes (most connected - your core abstractions)
1. `Санитизация базы MySQL` - 16 edges
2. `Роль языковой модели` - 6 edges
3. `Как устроено решение` - 4 edges
4. `Цикл автонастройки — как модель участвует в настройке` - 4 edges
5. `Текст задания` - 1 edges
6. `Что сделано — по каждому пункту проверки` - 1 edges
7. `Этап 1 — открытый инструмент` - 1 edges
8. `Этап 2 — доработка, ради которой всё и делалось` - 1 edges
9. `Как сквозная замена выглядит на самом деле` - 1 edges
10. `Из каких модулей состоит` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities (4 total, 0 thin omitted)

### Community 0 - "Санитизация базы MySQL"
Cohesion: 0.13
Nodes (14): Границы решения — чего оно не делает, Демо-данные, Допущения исполнителя, Из каких модулей состоит, Использованное открытое программное обеспечение, Как проверяется результат, Ключ замен, Код (+6 more)

### Community 1 - "Роль языковой модели"
Cohesion: 0.40
Nodes (5): Вторая роль модели — поиск имён в свободном тексте, Замер детектора, Почему модель не порождает замены, Роль языковой модели, Что модель делает

### Community 2 - "Как устроено решение"
Cohesion: 0.50
Nodes (4): Как сквозная замена выглядит на самом деле, Как устроено решение, Этап 1 — открытый инструмент, Этап 2 — доработка, ради которой всё и делалось

### Community 3 - "Цикл автонастройки — как модель участвует в настройке"
Cohesion: 0.50
Nodes (4): Почему цикл вынесен из рабочего прогона, Предохранители — и каждый закрывает конкретный способ всё сломать, Цикл автонастройки — как модель участвует в настройке, Что уже проверено

## Knowledge Gaps
- **23 isolated node(s):** `Текст задания`, `Что сделано — по каждому пункту проверки`, `Этап 1 — открытый инструмент`, `Этап 2 — доработка, ради которой всё и делалось`, `Как сквозная замена выглядит на самом деле` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 24 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Санитизация базы MySQL` connect `Санитизация базы MySQL` to `Роль языковой модели`, `Как устроено решение`?**
  _High betweenness centrality (0.880) - this node is a cross-community bridge._
- **Why does `Роль языковой модели` connect `Роль языковой модели` to `Санитизация базы MySQL`, `Цикл автонастройки — как модель участвует в настройке`?**
  _High betweenness centrality (0.496) - this node is a cross-community bridge._
- **Why does `Как устроено решение` connect `Как устроено решение` to `Санитизация базы MySQL`?**
  _High betweenness centrality (0.214) - this node is a cross-community bridge._
- **What connects `Текст задания`, `Что сделано — по каждому пункту проверки`, `Этап 1 — открытый инструмент` to the rest of the system?**
  _23 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Санитизация базы MySQL` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._