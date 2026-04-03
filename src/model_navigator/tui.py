from model_navigator.lineage import assign_columns
from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static
from textual.widget import Widget
from textual.reactive import reactive


class LineageGraph(Widget, can_focus=True):
    selected = reactive("", recompose=True)

    def __init__(self, graph: dict, selected: str):
        super().__init__(id="graph")
        self.graph = graph
        self.selected = selected

    def compose(self) -> ComposeResult:
        columns = assign_columns(self.graph)
        grouped: dict[int, list[str]] = {}
        for name, col in columns.items():
            grouped.setdefault(col, []).append(name)

        with Horizontal(id="columns"):
            for col_idx in sorted(grouped):
                with Vertical(classes="graph-column"):
                    for name in sorted(grouped[col_idx]):
                        classes = "node-box"
                        if name == self.selected:
                            classes += " selected"
                        yield Static(name, classes=classes)


class Inspector(Static):
    def show_model(self, name: str, index: int, total: int):
        title = Text(name, style="bold")

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold", width=10)
        details.add_column()
        details.add_row("Type", "model")
        details.add_row("Package", "my_project")
        details.add_row("Index", f"{index + 1} of {total}")

        upstream = Text("- stag_raw_data\n stg_events", style="dim")
        downstream = Text("- fct_output", style="dim")

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

    #columns {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    .node-box {
        width: 24;
        height: 3;
        content-align: center middle;
        border: round $warning;
        background: $panel;
        margin: 1;
    }

    .node-box.selected {
        border: round $success;
        background: $panel;
    }

    #col-upstream, #col-selected, #col-downstream {
        width: 1fr;
        height: auto;
        align: center middle;
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
        ("q", "quit", "Quit"),
    ]

    FAKE_GRAPH = {
        "stg_charges": {
            "type": "model",
            "upstream": [],
            "downstream": ["int_revenue", "fct_payments"],
        },
        "stg_users": {"type": "model", "upstream": [], "downstream": ["dim_customers"]},
        "int_revenue": {
            "type": "model",
            "upstream": ["stg_charges"],
            "downstream": ["fct_payments"],
        },
        "dim_customers": {
            "type": "model",
            "upstream": ["stg_users"],
            "downstream": ["fct_payments"],
        },
        "fct_payments": {
            "type": "model",
            "upstream": ["int_revenue", "dim_customers"],
            "downstream": [],
        },
    }

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield LineageGraph(self.FAKE_GRAPH, "int_revenue")
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
        current_col = columns[graph.selected]
        target_col = current_col + direction
        siblings = sorted(name for name, col in columns.items() if col == current_col)
        current_row = siblings.index(graph.selected)
        target_siblings = sorted(name for name, col in columns.items() if col == target_col)
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
        current_col = columns[graph.selected]
        siblings = sorted(name for name, col in columns.items() if col == current_col)
        current_idx = siblings.index(graph.selected)
        target_idx = current_idx + direction
        if 0 <= target_idx < len(siblings):
            graph.selected = siblings[target_idx]
            self._refresh_selection()

    def _refresh_selection(self):
        graph = self.query_one(LineageGraph)
        self.sub_title = graph.selected
        self.query_one(Inspector).show_model(graph.selected, 0, len(graph.graph))


def main() -> None:
    app = ModelNavigatorApp()
    app.run()
