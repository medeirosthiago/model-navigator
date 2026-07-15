from .dbt_graph import GraphNode


def lineage_columns(
    graph: dict[str, GraphNode],
    selected: str,
    visible: set[str] | None = None,
) -> dict[str, int]:
    columns = {selected: 0}
    included = set(graph) if visible is None else visible

    for direction, step in (("upstream", -1), ("downstream", 1)):
        frontier = [selected]
        while frontier:
            name = frontier.pop(0)
            neighbors = getattr(graph[name], direction)
            for neighbor in neighbors:
                if neighbor not in included:
                    continue
                candidate = columns[name] + step
                current = columns.get(neighbor)
                if current is not None and (
                    candidate >= current if step < 0 else candidate <= current
                ):
                    continue
                columns[neighbor] = candidate
                frontier.append(neighbor)

    return columns


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
