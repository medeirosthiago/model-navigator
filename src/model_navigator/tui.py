from model_navigator.lineage import assign_columns, nodes_with_depth, reachable_nodes
from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Static


class LineageGraph(Widget, can_focus=True):
    NODE_FOCUS = "node"
    LINEAGE_FOCUS = "lineage"
    BOX_WIDTH = 24
    BOX_HEIGHT = 3
    COLUMN_GAP = 8
    ROW_GAP = 2
    PADDING_X = 2
    PADDING_Y = 1
    CONNECTOR_STYLE = "#7f8fa6"
    BOX_FILL_STYLE = "on #253341"
    BOX_BORDER_STYLE = "#4f6375 on #253341"
    BOX_LABEL_STYLE = "#e6edf3 on #253341"
    SELECTED_BORDER_STYLE = "bold #ffb454 on #253341"
    SELECTED_LABEL_STYLE = "bold #f8fafc on #253341"
    CONNECTOR_CHARS = {
        frozenset(): " ",
        frozenset({"l"}): "─",
        frozenset({"r"}): "─",
        frozenset({"u"}): "│",
        frozenset({"d"}): "│",
        frozenset({"l", "r"}): "─",
        frozenset({"u", "d"}): "│",
        frozenset({"r", "d"}): "┌",
        frozenset({"l", "d"}): "┐",
        frozenset({"r", "u"}): "└",
        frozenset({"l", "u"}): "┘",
        frozenset({"l", "r", "d"}): "┬",
        frozenset({"l", "r", "u"}): "┴",
        frozenset({"u", "d", "r"}): "├",
        frozenset({"u", "d", "l"}): "┤",
        frozenset({"u", "d", "l", "r"}): "┼",
    }

    selected = reactive("")
    depth = reactive(2)
    focus_mode = reactive(NODE_FOCUS)

    def __init__(self, graph: dict, selected: str):
        super().__init__(id="graph")
        self.graph = graph
        self.selected = selected
        self.lineage_anchor = selected

    def visible_anchor(self) -> str:
        if self.focus_mode == self.LINEAGE_FOCUS:
            return self.lineage_anchor
        return self.selected

    def visible_nodes(self) -> set[str]:
        return nodes_with_depth(self.graph, self.visible_anchor(), self.depth)

    def set_focus_mode(self, mode: str) -> None:
        if mode == self.LINEAGE_FOCUS:
            self.lineage_anchor = self.selected
        self.focus_mode = mode

    def ensure_selection_visible(self) -> None:
        if self.focus_mode != self.LINEAGE_FOCUS:
            return
        columns = assign_columns(self.graph)
        if abs(columns[self.selected] - columns[self.lineage_anchor]) > self.depth:
            self.lineage_anchor = self.selected

    def focused_edges(self, visible: set[str]) -> set[tuple[str, str]]:
        upstream = reachable_nodes(self.graph, self.selected, "upstream")
        downstream = reachable_nodes(self.graph, self.selected, "downstream")
        upstream_path = upstream | {self.selected}
        downstream_path = downstream | {self.selected}
        edges = set()

        for child in visible:
            for parent in self.graph[child]["upstream"]:
                if parent not in visible:
                    continue
                on_upstream_path = parent in upstream and child in upstream_path
                on_downstream_path = parent in downstream_path and child in downstream
                if on_upstream_path or on_downstream_path:
                    edges.add((parent, child))

        return edges

    @staticmethod
    def _truncate_label(label: str, limit: int) -> str:
        if len(label) <= limit:
            return label
        return f"{label[: limit - 3]}..."

    def _layout_nodes(
        self,
        columns: dict[str, int],
        visible: set[str],
    ) -> tuple[dict[str, tuple[int, int]], int, int]:
        grouped: dict[int, list[str]] = {}
        for name, col in columns.items():
            if name in visible:
                grouped.setdefault(col, []).append(name)
        for names in grouped.values():
            names.sort()

        ordered_columns = sorted(grouped)
        max_rows = max((len(names) for names in grouped.values()), default=0)
        content_height = (
            max_rows * self.BOX_HEIGHT + max(max_rows - 1, 0) * self.ROW_GAP
        )
        canvas_width = (
            self.PADDING_X * 2
            + len(ordered_columns) * self.BOX_WIDTH
            + max(len(ordered_columns) - 1, 0) * self.COLUMN_GAP
        )
        canvas_height = self.PADDING_Y * 2 + content_height

        positions: dict[str, tuple[int, int]] = {}
        for column_index, column in enumerate(ordered_columns):
            x = self.PADDING_X + column_index * (self.BOX_WIDTH + self.COLUMN_GAP)
            column_height = (
                len(grouped[column]) * self.BOX_HEIGHT
                + max(len(grouped[column]) - 1, 0) * self.ROW_GAP
            )
            offset_y = self.PADDING_Y + max(0, (content_height - column_height) // 2)
            for row_index, name in enumerate(grouped[column]):
                y = offset_y + row_index * (self.BOX_HEIGHT + self.ROW_GAP)
                positions[name] = (x, y)

        return positions, canvas_width, canvas_height

    def _add_segment(
        self,
        directions: list[list[set[str]]],
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        x1, y1 = start
        x2, y2 = end

        if x1 == x2:
            step = 1 if y2 > y1 else -1
            y = y1
            while y != y2:
                next_y = y + step
                directions[y][x1].add("d" if step > 0 else "u")
                directions[next_y][x1].add("u" if step > 0 else "d")
                y = next_y
            return

        step = 1 if x2 > x1 else -1
        x = x1
        while x != x2:
            next_x = x + step
            directions[y1][x].add("r" if step > 0 else "l")
            directions[y1][next_x].add("l" if step > 0 else "r")
            x = next_x

    def _draw_edge(
        self,
        directions: list[list[set[str]]],
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> None:
        x1, y1 = start
        x2, y2 = end
        if x2 < x1:
            return
        if y1 == y2:
            self._add_segment(directions, start, end)
            return
        mid_x = x1 + max(1, (x2 - x1) // 2)
        self._add_segment(directions, start, (mid_x, y1))
        self._add_segment(directions, (mid_x, y1), (mid_x, y2))
        self._add_segment(directions, (mid_x, y2), end)

    @staticmethod
    def _set_cell(
        chars: list[list[str]],
        styles: list[list[str]],
        x: int,
        y: int,
        char: str,
        style: str,
    ) -> None:
        if 0 <= y < len(chars) and 0 <= x < len(chars[y]):
            chars[y][x] = char
            styles[y][x] = style

    def _draw_box(
        self,
        chars: list[list[str]],
        styles: list[list[str]],
        x: int,
        y: int,
        label: str,
        selected: bool,
    ) -> None:
        border_style = self.SELECTED_BORDER_STYLE if selected else self.BOX_BORDER_STYLE
        label_style = self.SELECTED_LABEL_STYLE if selected else self.BOX_LABEL_STYLE
        text = self._truncate_label(label, self.BOX_WIDTH - 2).center(
            self.BOX_WIDTH - 2
        )

        for offset in range(1, self.BOX_WIDTH - 1):
            self._set_cell(chars, styles, x + offset, y, "─", border_style)
            self._set_cell(
                chars,
                styles,
                x + offset,
                y + self.BOX_HEIGHT - 1,
                "─",
                border_style,
            )
        self._set_cell(chars, styles, x, y, "╭", border_style)
        self._set_cell(chars, styles, x + self.BOX_WIDTH - 1, y, "╮", border_style)
        self._set_cell(
            chars,
            styles,
            x,
            y + self.BOX_HEIGHT - 1,
            "╰",
            border_style,
        )
        self._set_cell(
            chars,
            styles,
            x + self.BOX_WIDTH - 1,
            y + self.BOX_HEIGHT - 1,
            "╯",
            border_style,
        )

        self._set_cell(chars, styles, x, y + 1, "│", border_style)
        self._set_cell(
            chars,
            styles,
            x + self.BOX_WIDTH - 1,
            y + 1,
            "│",
            border_style,
        )
        for offset, char in enumerate(text, start=1):
            style = label_style if char.strip() else self.BOX_FILL_STYLE
            self._set_cell(chars, styles, x + offset, y + 1, char, style)

    def _content_bounds(
        self, positions: dict[str, tuple[int, int]], width: int, height: int
    ) -> tuple[int, int, int, int]:
        if not positions:
            return (0, 0, width, height)

        min_x = min(x for x, _ in positions.values())
        min_y = min(y for _, y in positions.values())
        max_x = max(x + self.BOX_WIDTH for x, _ in positions.values())
        max_y = max(y + self.BOX_HEIGHT for _, y in positions.values())
        return min_x, min_y, max_x, max_y

    def _focus_point(
        self,
        positions: dict[str, tuple[int, int]],
        width: int,
        height: int,
    ) -> tuple[int, int]:
        if self.focus_mode == self.NODE_FOCUS and self.selected in positions:
            selected_x, selected_y = positions[self.selected]
            return (
                selected_x + self.BOX_WIDTH // 2,
                selected_y + self.BOX_HEIGHT // 2,
            )

        min_x, min_y, max_x, max_y = self._content_bounds(positions, width, height)
        return ((min_x + max_x) // 2, (min_y + max_y) // 2)

    def _render_viewport(
        self,
        chars: list[list[str]],
        styles: list[list[str]],
        positions: dict[str, tuple[int, int]],
        focus_point: tuple[int, int],
    ) -> Group:
        viewport_width = max(self.size.width, 1)
        viewport_height = max(self.size.height, 1)
        focus_x, focus_y = focus_point
        origin_x = focus_x - viewport_width // 2
        origin_y = focus_y - viewport_height // 2

        if self.focus_mode == self.LINEAGE_FOCUS and self.selected in positions:
            selected_x, selected_y = positions[self.selected]
            selected_right = selected_x + self.BOX_WIDTH
            selected_bottom = selected_y + self.BOX_HEIGHT
            margin_x = min(
                max((viewport_width - self.BOX_WIDTH) // 2, 0), self.BOX_WIDTH
            )
            margin_y = min(
                max((viewport_height - self.BOX_HEIGHT) // 2, 0), self.ROW_GAP + 1
            )

            min_selected_x = origin_x + margin_x
            max_selected_right = origin_x + viewport_width - margin_x
            if selected_x < min_selected_x:
                origin_x = selected_x - margin_x
            elif selected_right > max_selected_right:
                origin_x = selected_right + margin_x - viewport_width

            min_selected_y = origin_y + margin_y
            max_selected_bottom = origin_y + viewport_height - margin_y
            if selected_y < min_selected_y:
                origin_y = selected_y - margin_y
            elif selected_bottom > max_selected_bottom:
                origin_y = selected_bottom + margin_y - viewport_height

        lines: list[Text] = []
        for viewport_y in range(viewport_height):
            canvas_y = origin_y + viewport_y
            line = Text(no_wrap=True, overflow="ignore")
            for viewport_x in range(viewport_width):
                canvas_x = origin_x + viewport_x
                if 0 <= canvas_y < len(chars) and 0 <= canvas_x < len(chars[canvas_y]):
                    line.append(chars[canvas_y][canvas_x], styles[canvas_y][canvas_x])
                else:
                    line.append(" ")
            lines.append(line)

        return Group(*lines)

    def render(self) -> Group:
        columns = assign_columns(self.graph)
        visible = self.visible_nodes()
        focused_edges = self.focused_edges(visible)
        positions, width, height = self._layout_nodes(columns, visible)
        chars = [[" " for _ in range(width)] for _ in range(height)]
        styles = [["" for _ in range(width)] for _ in range(height)]
        directions = [[set() for _ in range(width)] for _ in range(height)]

        for parent, child in focused_edges:
            child_x, child_y = positions[child]
            end = (child_x - 1, child_y + self.BOX_HEIGHT // 2)
            parent_x, parent_y = positions[parent]
            start = (parent_x + self.BOX_WIDTH, parent_y + self.BOX_HEIGHT // 2)
            self._draw_edge(directions, start, end)

        for y, row in enumerate(directions):
            for x, cell in enumerate(row):
                if cell:
                    chars[y][x] = self.CONNECTOR_CHARS[frozenset(cell)]
                    styles[y][x] = self.CONNECTOR_STYLE

        for name, (x, y) in positions.items():
            self._draw_box(chars, styles, x, y, name, name == self.selected)

        focus_point = self._focus_point(positions, width, height)
        return self._render_viewport(chars, styles, positions, focus_point)


class Inspector(Static):
    @staticmethod
    def _format_relations(names: list[str]) -> Text:
        if not names:
            return Text("none", style="dim")
        return Text("\n".join(f"- {name}" for name in names), style="dim")

    def show_model(
        self,
        graph: dict,
        name: str,
        depth: int,
        visible: set[str],
        focus_mode: str,
        center: str,
    ):
        node = graph[name]
        columns = assign_columns(graph)
        title = Text(name, style="bold")

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold", width=10)
        details.add_column()
        details.add_row("Type", str(node.get("type", "model")))
        details.add_row("Package", "my_project")
        details.add_row("Column", str(columns[name]))
        details.add_row("Depth", str(depth))
        details.add_row("Focus", focus_mode)
        details.add_row("Center", center)
        details.add_row("Visible", f"{len(visible)} of {len(graph)}")

        upstream = self._format_relations(node["upstream"])
        downstream = self._format_relations(node["downstream"])

        self.update(
            Group(
                title,
                Rule(style="dim"),
                details,
                Rule(title="Upstream", style="dim"),
                upstream,
                Rule(title="Downstream", style="dim"),
                downstream,
            )
        )


class ModelNavigatorApp(App[None]):
    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    #body {
        height: 1fr;
    }

    #graph {
        width: 1fr;
        height: 1fr;
        align: center middle;
        border: round $secondary;
        background: $surface;
    }

    #inspector {
        width: 38;
        height: 1fr;
        border: round $secondary;
        background: $surface;
        padding: 1 2;
    }

    Footer {
        background: $background;
        color: $secondary;
    }
    """

    BINDINGS = [
        ("left", "select_prev", "Previous"),
        ("right", "select_next", "Next"),
        ("up", "select_up", "Up"),
        ("down", "select_down", "Down"),
        ("f", "toggle_focus", "Focus"),
        ("[", "decrease_depth", "Depth-"),
        ("]", "increase_depth", "Depth+"),
        ("q", "quit", "Quit"),
    ]

    FAKE_GRAPH = {
        "raw_stripe_charges": {
            "type": "source",
            "upstream": [],
            "downstream": ["stg_charges"],
        },
        "raw_stripe_refunds": {
            "type": "source",
            "upstream": [],
            "downstream": ["stg_refunds"],
        },
        "raw_app_users": {
            "type": "source",
            "upstream": [],
            "downstream": ["stg_users"],
        },
        "seed_exchange_rates": {
            "type": "seed",
            "upstream": [],
            "downstream": ["dim_fx_rates"],
        },
        "stg_charges": {
            "type": "model",
            "upstream": ["raw_stripe_charges"],
            "downstream": ["int_revenue"],
        },
        "stg_refunds": {
            "type": "model",
            "upstream": ["raw_stripe_refunds"],
            "downstream": ["int_refunds"],
        },
        "stg_users": {
            "type": "model",
            "upstream": ["raw_app_users"],
            "downstream": ["dim_customers"],
        },
        "int_revenue": {
            "type": "model",
            "upstream": ["stg_charges"],
            "downstream": ["fct_payments"],
        },
        "int_refunds": {
            "type": "model",
            "upstream": ["stg_refunds"],
            "downstream": ["fct_payments"],
        },
        "dim_customers": {
            "type": "model",
            "upstream": ["stg_users"],
            "downstream": ["fct_payments", "mart_customer_ltv"],
        },
        "dim_fx_rates": {
            "type": "model",
            "upstream": ["seed_exchange_rates"],
            "downstream": ["mart_revenue_daily"],
        },
        "fct_payments": {
            "type": "model",
            "upstream": ["int_revenue", "int_refunds", "dim_customers"],
            "downstream": ["mart_revenue_daily", "mart_customer_ltv"],
        },
        "mart_revenue_daily": {
            "type": "model",
            "upstream": ["fct_payments", "dim_fx_rates"],
            "downstream": ["dashboard_finance"],
        },
        "mart_customer_ltv": {
            "type": "model",
            "upstream": ["fct_payments", "dim_customers"],
            "downstream": ["dashboard_customers"],
        },
        "dashboard_finance": {
            "type": "exposure",
            "upstream": ["mart_revenue_daily"],
            "downstream": [],
        },
        "dashboard_customers": {
            "type": "exposure",
            "upstream": ["mart_customer_ltv"],
            "downstream": [],
        },
    }

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield LineageGraph(self.FAKE_GRAPH, "fct_payments")
            yield Inspector("Inspector", id="inspector")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Model Navigator"
        self._refresh_selection()

    def action_select_prev(self):
        self._move_horizontal(-1)

    def action_select_next(self):
        self._move_horizontal(1)

    def _move_horizontal(self, direction: int):
        graph = self.query_one(LineageGraph)
        columns = assign_columns(graph.graph)
        visible = graph.visible_nodes()
        current_col = columns[graph.selected]
        target_col = current_col + direction
        siblings = sorted(name for name in visible if columns[name] == current_col)
        current_row = siblings.index(graph.selected)
        target_siblings = sorted(
            name for name in visible if columns[name] == target_col
        )
        if not target_siblings:
            return
        target_row = min(current_row, len(target_siblings) - 1)
        graph.selected = target_siblings[target_row]
        self._refresh_selection()

    def action_select_up(self):
        self._move_vertical(-1)

    def action_select_down(self):
        self._move_vertical(1)

    def _move_vertical(self, direction: int):
        graph = self.query_one(LineageGraph)
        columns = assign_columns(graph.graph)
        visible = graph.visible_nodes()
        current_col = columns[graph.selected]
        siblings = sorted(name for name in visible if columns[name] == current_col)
        current_idx = siblings.index(graph.selected)
        target_idx = current_idx + direction
        if 0 <= target_idx < len(siblings):
            graph.selected = siblings[target_idx]
            self._refresh_selection()

    def action_decrease_depth(self):
        graph = self.query_one(LineageGraph)
        if graph.depth == 0:
            return
        graph.depth -= 1
        graph.ensure_selection_visible()
        self.notify(f"Depth: {graph.depth}")
        self._refresh_selection()

    def action_increase_depth(self):
        graph = self.query_one(LineageGraph)
        max_depth = len(graph.graph) - 1
        if graph.depth >= max_depth:
            return
        graph.depth += 1
        graph.ensure_selection_visible()
        self.notify(f"Depth: {graph.depth}")
        self._refresh_selection()

    def action_toggle_focus(self):
        graph = self.query_one(LineageGraph)
        next_mode = (
            LineageGraph.LINEAGE_FOCUS
            if graph.focus_mode == LineageGraph.NODE_FOCUS
            else LineageGraph.NODE_FOCUS
        )
        graph.set_focus_mode(next_mode)
        self.notify(f"Focus: {graph.focus_mode}")
        self._refresh_selection()

    def _refresh_selection(self):
        graph = self.query_one(LineageGraph)
        visible = graph.visible_nodes()
        center = graph.visible_anchor()
        self.sub_title = (
            f"{graph.selected} | depth {graph.depth} | focus {graph.focus_mode}"
        )
        self.query_one(Inspector).show_model(
            graph.graph,
            graph.selected,
            graph.depth,
            visible,
            graph.focus_mode,
            center,
        )


def main() -> None:
    app = ModelNavigatorApp()
    app.run()
