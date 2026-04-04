def assign_columns(graph: dict) -> dict[str, int]:
    columns = {}

    def walk(name: str) -> int:
        if name in columns:
            return columns[name]
        node = graph[name]
        if not node["upstream"]:
            columns[name] = 0
            return 0
        col = max(walk(parent) for parent in node["upstream"]) + 1
        columns[name] = col
        return col

    for name in graph:
        walk(name)
    return columns


def nodes_with_depth(graph: dict, selected: str, depth: int) -> set[str]:
    columns = assign_columns(graph)
    selected_column = columns[selected]
    min_column = selected_column - max(depth, 0)
    max_column = selected_column + max(depth, 0)

    return {
        name for name, column in columns.items() if min_column <= column <= max_column
    }
