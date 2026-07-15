from .dbt_graph import GraphNode


def assign_columns(graph: dict[str, GraphNode]) -> dict[str, int]:
    columns = {}

    def walk(name: str) -> int:
        if name in columns:
            return columns[name]
        node = graph[name]
        if not node.upstream:
            columns[name] = 0
            return 0
        col = max(walk(parent) for parent in node.upstream) + 1
        columns[name] = col
        return col

    for name in graph:
        walk(name)
    return columns


def lineage_columns(
    graph: dict[str, GraphNode],
    selected: str,
) -> dict[str, int]:
    columns = {selected: 0}

    for direction, step in (("upstream", -1), ("downstream", 1)):
        frontier = [(selected, 0)]
        seen = {selected}
        while frontier:
            name, distance = frontier.pop(0)
            neighbors = getattr(graph[name], direction)
            for neighbor in neighbors:
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                columns.setdefault(neighbor, (distance + 1) * step)
                frontier.append((neighbor, distance + 1))

    return columns


def nodes_with_depth(
    graph: dict[str, GraphNode],
    selected: str,
    depth: int,
) -> set[str]:
    columns = assign_columns(graph)
    selected_column = columns[selected]
    min_column = selected_column - max(depth, 0)
    max_column = selected_column + max(depth, 0)

    return {
        name for name, column in columns.items() if min_column <= column <= max_column
    }


def lineage_nodes_with_depth(
    graph: dict[str, GraphNode],
    selected: str,
    depth: int,
) -> set[str]:
    max_depth = max(depth, 0)
    visible = {selected}

    for direction in ("upstream", "downstream"):
        frontier = [(selected, 0)]
        while frontier:
            name, current_depth = frontier.pop(0)
            if current_depth >= max_depth:
                continue
            neighbors = (
                graph[name].upstream
                if direction == "upstream"
                else graph[name].downstream
            )
            for neighbor in neighbors:
                if neighbor in visible:
                    continue
                visible.add(neighbor)
                frontier.append((neighbor, current_depth + 1))

    return visible


def reachable_nodes(
    graph: dict[str, GraphNode],
    selected: str,
    direction: str,
) -> set[str]:
    seen = set()
    frontier = [selected]

    while frontier:
        name = frontier.pop()
        neighbors = (
            graph[name].upstream if direction == "upstream" else graph[name].downstream
        )
        for neighbor in neighbors:
            if neighbor in seen:
                continue
            seen.add(neighbor)
            frontier.append(neighbor)

    return seen


def selected_lineage(
    graph: dict[str, GraphNode],
    selected: str,
) -> set[str]:
    return (
        reachable_nodes(graph, selected, "upstream")
        | {selected}
        | reachable_nodes(graph, selected, "downstream")
    )
