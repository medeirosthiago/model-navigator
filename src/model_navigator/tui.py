import os
import shlex
import shutil
import subprocess

from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Input, OptionList, Static

from .dbt_graph import GraphNode, ManifestGraph
from .lineage import assign_columns, nodes_with_depth, reachable_nodes, selected_lineage


class LineageGraph(Widget, can_focus=True):
    NODE_FOCUS = "node"
    LINEAGE_FOCUS = "lineage"
    WINDOW_VIEW = "window"
    SELECTED_LINEAGE_VIEW = "selected_lineage"
    BOX_WIDTH = 30
    BOX_HEIGHT = 3
    COLUMN_GAP = 8
    ROW_GAP = 2
    PADDING_X = 2
    PADDING_Y = 1
    CONNECTOR_STYLE = "#a0a0a0"
    BOX_FILL_STYLE = "on #1e1e1e"
    BOX_BORDER_STYLE = "#555555 on #1e1e1e"
    BOX_LABEL_STYLE = "#e0e0e0 on #1e1e1e"
    SELECTED_BORDER_STYLE = "bold #0178d4 on #1e1e1e"
    SELECTED_LABEL_STYLE = "bold #ffffff on #1e1e1e"
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
    view_mode = reactive(SELECTED_LINEAGE_VIEW)

    def __init__(
        self,
        graph: ManifestGraph,
        selected: str,
        depth: int = 2,
    ) -> None:
        super().__init__(id="graph")
        self.graph = graph
        self.selected = selected
        self.depth = max(depth, 0)
        self.lineage_anchor = selected
        self.lineage_view_anchor = selected

    def sort_key(self, node_id: str) -> tuple[str, str]:
        node = self.graph.nodes[node_id]
        return (node.label.casefold(), node.unique_id.casefold())

    def view_label(self) -> str:
        if self.view_mode == self.SELECTED_LINEAGE_VIEW:
            return "selected lineage"
        return "column window"

    def visible_anchor(self) -> str:
        if self.view_mode == self.SELECTED_LINEAGE_VIEW:
            if self.focus_mode == self.LINEAGE_FOCUS:
                return self.lineage_anchor
            return self.selected
        if self.focus_mode == self.LINEAGE_FOCUS:
            return self.lineage_anchor
        return self.selected

    def visible_nodes(self) -> set[str]:
        if self.view_mode == self.SELECTED_LINEAGE_VIEW:
            return selected_lineage(
                self.graph.nodes,
                self.lineage_view_anchor,
            ) & nodes_with_depth(
                self.graph.nodes,
                self.visible_anchor(),
                self.depth,
            )
        return nodes_with_depth(self.graph.nodes, self.visible_anchor(), self.depth)

    def set_view_mode(self, mode: str) -> None:
        if mode == self.SELECTED_LINEAGE_VIEW:
            self.lineage_view_anchor = self.selected
            self.lineage_anchor = self.selected
        self.view_mode = mode
        if mode == self.WINDOW_VIEW and self.focus_mode == self.LINEAGE_FOCUS:
            self.lineage_anchor = self.selected
        self.refresh()

    def set_focus_mode(self, mode: str) -> None:
        if mode == self.LINEAGE_FOCUS:
            self.lineage_anchor = self.selected
        self.focus_mode = mode

    def ensure_selection_visible(self) -> None:
        if self.focus_mode != self.LINEAGE_FOCUS:
            return
        columns = assign_columns(self.graph.nodes)
        if abs(columns[self.selected] - columns[self.visible_anchor()]) > self.depth:
            self.lineage_anchor = self.selected

    def focused_edges(self, visible: set[str]) -> set[tuple[str, str]]:
        upstream = reachable_nodes(self.graph.nodes, self.selected, "upstream")
        downstream = reachable_nodes(self.graph.nodes, self.selected, "downstream")
        upstream_path = upstream | {self.selected}
        downstream_path = downstream | {self.selected}
        edges = set()

        for child in visible:
            for parent in self.graph.nodes[child].upstream:
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
        for node_id, column in columns.items():
            if node_id in visible:
                grouped.setdefault(column, []).append(node_id)
        for node_ids in grouped.values():
            node_ids.sort(key=self.sort_key)

        ordered_columns = sorted(grouped)
        max_rows = max((len(node_ids) for node_ids in grouped.values()), default=0)
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
            for row_index, node_id in enumerate(grouped[column]):
                y = offset_y + row_index * (self.BOX_HEIGHT + self.ROW_GAP)
                positions[node_id] = (x, y)

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
        self,
        positions: dict[str, tuple[int, int]],
        width: int,
        height: int,
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
                max((viewport_width - self.BOX_WIDTH) // 2, 0),
                self.BOX_WIDTH,
            )
            margin_y = min(
                max((viewport_height - self.BOX_HEIGHT) // 2, 0),
                self.ROW_GAP + 1,
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
        columns = assign_columns(self.graph.nodes)
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

        for node_id, (x, y) in positions.items():
            self._draw_box(
                chars,
                styles,
                x,
                y,
                self.graph.nodes[node_id].label,
                node_id == self.selected,
            )

        focus_point = self._focus_point(positions, width, height)
        return self._render_viewport(chars, styles, positions, focus_point)


class Inspector(Static):
    @staticmethod
    def _format_relations(
        graph: ManifestGraph,
        node_ids: tuple[str, ...],
    ) -> Text:
        if not node_ids:
            return Text("none", style="dim")

        lines = [f"- {graph.nodes[node_id].label}" for node_id in node_ids]
        return Text("\n".join(lines), style="dim")

    def show_model(
        self,
        graph: ManifestGraph,
        node_id: str,
        depth: int,
        visible: set[str],
        focus_mode: str,
        view_mode: str,
        center: str,
    ) -> None:
        node = graph.nodes[node_id]
        columns = assign_columns(graph.nodes)
        title = Text(node.label, style="bold")
        file_path = Text(
            str(node.file_path) if node.file_path else "file unavailable",
            style="dim",
        )
        depth_label = str(depth)
        view_label = (
            "selected lineage"
            if view_mode == LineageGraph.SELECTED_LINEAGE_VIEW
            else "column window"
        )

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold", width=10)
        details.add_column()
        details.add_row("Type", node.resource_type)
        details.add_row("Package", node.package_name)
        details.add_row("Project", graph.metadata.project_name)
        details.add_row("Column", str(columns[node_id]))
        details.add_row("Depth", depth_label)
        details.add_row("View", view_label)
        details.add_row("Focus", focus_mode)
        details.add_row("Center", graph.nodes[center].label)
        details.add_row("Visible", f"{len(visible)} of {len(graph.nodes)}")

        upstream = self._format_relations(graph, node.upstream)
        downstream = self._format_relations(graph, node.downstream)

        self.update(
            Group(
                title,
                Text(node.unique_id, style="dim"),
                file_path,
                Rule(style="dim"),
                details,
                Rule(title="Upstream", style="dim"),
                upstream,
                Rule(title="Downstream", style="dim"),
                downstream,
            )
        )


HELP_TEXT = """\
Model Navigator — Keyboard Shortcuts
========================================

Navigation
  h/l           Previous/next node
  j/k           Node below/above
  Arrow keys    Previous/next/below/above

Graph
  /             Search nodes
  f             Toggle focus mode
  v             Toggle view
  [/]           Decrease/increase depth
  d             Toggle inspector

Other
  Enter         Open in editor
  ?             Show this help
  Ctrl-Q        Quit
"""


class HelpScreen(Screen):
    """Simple scrollable help screen."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=False),

    ]
    DEFAULT_CSS = """
    HelpScreen { padding: 1 2; }
    HelpScreen Static { width: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)


class ModelNavigatorApp(App[None]):
    ENABLE_COMMAND_PALETTE = False
    ESCAPE_TO_MINIMIZE = False

    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    #body {
        height: 1fr;
    }

    #graph {
        width: 3fr;
        height: 1fr;
        align: center middle;
        border: tall $accent;
        background: $surface;
    }

    #inspector {
        width: 1fr;
        height: 1fr;
        border: tall $accent;
        background: $surface;
        padding: 1 2;
    }

    #node-picker {
        display: none;
        height: auto;
        max-height: 16;
        border: tall $accent;
    }
    #node-filter {
        height: 3;
    }
    #node-list {
        height: auto;
        max-height: 12;
    }
    """

    BINDINGS = [
        Binding("left", "select_prev", "Previous", show=False),
        Binding("right", "select_next", "Next", show=False),
        Binding("up", "select_up", "Up", show=False),
        Binding("down", "select_down", "Down", show=False),
        Binding("enter", "open_selected", "Open", show=False),
        Binding("slash", "open_node_picker", "Search", show=False),
        Binding("f", "toggle_focus", "Focus", show=False),
        Binding("v", "toggle_view", "View", show=False),
        Binding("bracketleft", "decrease_depth", "Depth-", show=False),
        Binding("bracketright", "increase_depth", "Depth+", show=False),
        Binding("d", "toggle_inspector", "Inspector", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    def __init__(
        self,
        graph: ManifestGraph,
        initial_selected: str,
        initial_depth: int,
    ) -> None:
        super().__init__()
        self.graph = graph
        self.initial_selected = initial_selected
        self.initial_depth = max(initial_depth, 0)
        self._filtered_nodes: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield LineageGraph(self.graph, self.initial_selected, self.initial_depth)
            yield Inspector("Inspector", id="inspector")
        with Vertical(id="node-picker"):
            yield Input(placeholder="Search nodes…", id="node-filter")
            yield OptionList(id="node-list")

    def on_mount(self) -> None:
        self.title = "Model Navigator"
        self._refresh_selection()

    @property
    def current_selected(self) -> str:
        return self.query_one(LineageGraph).selected

    def searchable_nodes(self) -> list[str]:
        return sorted(
            self.graph.nodes,
            key=lambda node_id: (
                self.graph.nodes[node_id].resource_type != "model",
                self.graph.nodes[node_id].label.casefold(),
            ),
        )

    def discovery_nodes(self) -> list[str]:
        ranked = sorted(
            self.graph.nodes,
            key=lambda node_id: (
                self.graph.nodes[node_id].resource_type != "model",
                -(
                    len(self.graph.nodes[node_id].upstream)
                    + len(self.graph.nodes[node_id].downstream)
                ),
                self.graph.nodes[node_id].label.casefold(),
            ),
        )
        return ranked[:10]

    def on_key(self, event: Key) -> None:
        if self._picker_active():
            if event.key == "escape":
                self._dismiss_picker()
                event.prevent_default()
                event.stop()
            elif event.key in ("down", "up"):
                self._navigate_option_list(event)
            return

        if event.key == "h":
            self.action_select_prev()
            event.prevent_default()
            event.stop()
        elif event.key == "j":
            self.action_select_down()
            event.prevent_default()
            event.stop()
        elif event.key == "k":
            self.action_select_up()
            event.prevent_default()
            event.stop()
        elif event.key == "l":
            self.action_select_next()
            event.prevent_default()
            event.stop()

    def _picker_active(self) -> bool:
        return self.query_one("#node-picker", Vertical).display

    def _dismiss_picker(self) -> None:
        self.query_one("#node-picker", Vertical).display = False
        self.query_one(LineageGraph).focus()

    def _navigate_option_list(self, event: Key) -> None:
        opt = self.query_one("#node-list", OptionList)
        if opt.option_count == 0:
            return
        idx = opt.highlighted or 0
        if event.key == "down":
            opt.highlighted = min(idx + 1, opt.option_count - 1)
            event.prevent_default()
            event.stop()
        elif event.key == "up":
            opt.highlighted = max(idx - 1, 0)
            event.prevent_default()
            event.stop()

    def action_open_node_picker(self) -> None:
        picker = self.query_one("#node-picker", Vertical)
        inp = self.query_one("#node-filter", Input)
        inp.value = ""
        picker.display = True
        self._populate_node_list("")
        inp.focus()

    def _populate_node_list(self, query: str) -> None:
        opt = self.query_one("#node-list", OptionList)
        opt.clear_options()
        self._filtered_nodes.clear()
        q = query.strip().lower()
        for node_id in self.searchable_nodes():
            node = self.graph.nodes[node_id]
            if not q or q in node.label.lower() or q in node.name.lower():
                opt.add_option(node.label)
                self._filtered_nodes.append(node_id)
        if self._filtered_nodes:
            opt.highlighted = 0

    @on(Input.Changed, "#node-filter")
    def _on_node_filter_changed(self, event: Input.Changed) -> None:
        self._populate_node_list(event.value)

    @on(Input.Submitted, "#node-filter")
    def _on_node_filter_submitted(self, event: Input.Submitted) -> None:
        opt = self.query_one("#node-list", OptionList)
        if self._filtered_nodes and opt.highlighted is not None:
            self._select_filtered_node(opt.highlighted)
        else:
            self._dismiss_picker()

    @on(OptionList.OptionSelected, "#node-list")
    def _on_node_selected(self, event: OptionList.OptionSelected) -> None:
        self._select_filtered_node(event.option_index)

    def _select_filtered_node(self, option_idx: int) -> None:
        if option_idx < 0 or option_idx >= len(self._filtered_nodes):
            return
        node_id = self._filtered_nodes[option_idx]
        self._dismiss_picker()
        self.select_node(node_id, isolate=True)

    def action_select_prev(self) -> None:
        self._move_horizontal(-1)

    def action_select_next(self) -> None:
        self._move_horizontal(1)

    def _sorted_visible_nodes(
        self,
        graph_widget: LineageGraph,
        visible: set[str],
        column: int,
        columns: dict[str, int],
    ) -> list[str]:
        return sorted(
            (node_id for node_id in visible if columns[node_id] == column),
            key=graph_widget.sort_key,
        )

    def _move_horizontal(self, direction: int) -> None:
        graph_widget = self.query_one(LineageGraph)
        columns = assign_columns(graph_widget.graph.nodes)
        visible = graph_widget.visible_nodes()
        current_col = columns[graph_widget.selected]
        target_col = current_col + direction
        siblings = self._sorted_visible_nodes(
            graph_widget,
            visible,
            current_col,
            columns,
        )
        current_row = siblings.index(graph_widget.selected)
        target_siblings = self._sorted_visible_nodes(
            graph_widget,
            visible,
            target_col,
            columns,
        )
        if not target_siblings:
            return
        target_row = min(current_row, len(target_siblings) - 1)
        graph_widget.selected = target_siblings[target_row]
        self._refresh_selection()

    def action_select_up(self) -> None:
        self._move_vertical(-1)

    def action_select_down(self) -> None:
        self._move_vertical(1)

    def _move_vertical(self, direction: int) -> None:
        graph_widget = self.query_one(LineageGraph)
        columns = assign_columns(graph_widget.graph.nodes)
        visible = graph_widget.visible_nodes()
        current_col = columns[graph_widget.selected]
        siblings = self._sorted_visible_nodes(
            graph_widget,
            visible,
            current_col,
            columns,
        )
        current_idx = siblings.index(graph_widget.selected)
        target_idx = current_idx + direction
        if 0 <= target_idx < len(siblings):
            graph_widget.selected = siblings[target_idx]
            self._refresh_selection()

    def action_decrease_depth(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        if graph_widget.depth == 0:
            return
        graph_widget.depth -= 1
        graph_widget.ensure_selection_visible()
        self.notify(f"Depth: {graph_widget.depth}")
        self._refresh_selection()

    def action_increase_depth(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        max_depth = len(graph_widget.graph.nodes) - 1
        if graph_widget.depth >= max_depth:
            return
        graph_widget.depth += 1
        graph_widget.ensure_selection_visible()
        self.notify(f"Depth: {graph_widget.depth}")
        self._refresh_selection()

    def action_toggle_focus(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        next_mode = (
            LineageGraph.LINEAGE_FOCUS
            if graph_widget.focus_mode == LineageGraph.NODE_FOCUS
            else LineageGraph.NODE_FOCUS
        )
        graph_widget.set_focus_mode(next_mode)
        self.notify(f"Focus: {graph_widget.focus_mode}")
        self._refresh_selection()

    def action_toggle_view(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        if graph_widget.view_mode == LineageGraph.WINDOW_VIEW:
            self.show_selected_lineage()
        else:
            self.show_full_graph()

    def action_open_selected(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        node = self.graph.nodes[graph_widget.selected]
        if node.file_path is None:
            self.notify(
                "This node does not have a file path in the manifest.",
                severity="warning",
            )
            return
        if not node.file_path.exists():
            self.notify(f"File does not exist: {node.file_path}", severity="warning")
            return

        editor_command = _resolve_editor_command()
        if editor_command is None:
            self.notify(
                "Set $EDITOR or install nvim, vim, or vi to open files.",
                severity="warning",
            )
            return

        command = [*editor_command, str(node.file_path)]

        try:
            if _editor_runs_in_terminal(editor_command):
                # Suspend the app so a terminal editor can take over cleanly.
                with self.suspend():
                    subprocess.run(command, check=False)
            else:
                # GUI editors can open above an integrated terminal without blanking the TUI.
                subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except Exception as error:  # pragma: no cover - defensive runtime path
            self.notify(f"Could not open editor: {error}", severity="error")
            return

        graph_widget.refresh()
        self._refresh_selection()

    def select_node(self, node_id: str, isolate: bool = False) -> None:
        graph_widget = self.query_one(LineageGraph)
        graph_widget.selected = node_id
        if isolate:
            graph_widget.set_view_mode(LineageGraph.SELECTED_LINEAGE_VIEW)
        graph_widget.ensure_selection_visible()
        self._refresh_selection()

    def show_selected_lineage(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        graph_widget.set_view_mode(LineageGraph.SELECTED_LINEAGE_VIEW)
        self.notify("View: selected lineage")
        self._refresh_selection()

    def show_full_graph(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        graph_widget.set_view_mode(LineageGraph.WINDOW_VIEW)
        graph_widget.ensure_selection_visible()
        self.notify("View: column window")
        self._refresh_selection()

    def action_toggle_inspector(self) -> None:
        inspector = self.query_one("#inspector", Inspector)
        inspector.display = not inspector.display

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def _refresh_selection(self) -> None:
        graph_widget = self.query_one(LineageGraph)
        visible = graph_widget.visible_nodes()
        center = graph_widget.visible_anchor()
        selected_node: GraphNode = self.graph.nodes[graph_widget.selected]
        depth_label = str(graph_widget.depth)
        self.sub_title = f"{selected_node.label} | view {graph_widget.view_label()} | depth {depth_label} | focus {graph_widget.focus_mode}"
        inspector = self.query_one("#inspector", Inspector)
        if inspector.display:
            inspector.show_model(
                self.graph,
                graph_widget.selected,
                graph_widget.depth,
                visible,
                graph_widget.focus_mode,
                graph_widget.view_mode,
                center,
            )


def _resolve_editor_command() -> list[str] | None:
    for variable in ("VISUAL", "EDITOR"):
        editor = os.environ.get(variable)
        if editor:
            return shlex.split(editor)
    for candidate in ("nvim", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]
    return None


def _editor_runs_in_terminal(editor_command: list[str]) -> bool:
    editor_name = os.path.basename(editor_command[0]).casefold()
    return editor_name not in {"cursor", "zed"}
