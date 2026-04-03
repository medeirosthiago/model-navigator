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
        node = self.graph[self.selected]
        with Horizontal(id="columns"):
            with Vertical(id="col-upstream"):
                for name in node["upstream"]:
                    yield Static(name, classes="node-box upstream")
            with Vertical(id="col-selected"):
                yield Static(self.selected, classes="node-box selected")
            with Vertical(id="col-downstream"):
                for name in node["downstream"]:
                    yield Static(name, classes="node-box downstream")


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
        border: round $accent;
        background: $panel;
        margin: 1;
    }

    .node-box.selected {
        border: round $warning;
        background: $boost;
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
        ("escape", "quit", "Quit"),
        ("left", "select_prev", "Previous"),
        ("right", "select_next", "Next"),
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
        graph = self.query_one(LineageGraph)
        node = graph.graph[graph.selected]
        if node["upstream"]:
            graph.selected = node["upstream"][0]
            self._refresh_selection()

    def action_select_next(self):
        graph = self.query_one(LineageGraph)
        node = graph.graph[graph.selected]
        if node["downstream"]:
            graph.selected = node["downstream"][0]
            self._refresh_selection()

    def _refresh_selection(self):
        graph = self.query_one(LineageGraph)
        self.sub_title = graph.selected
        self.query_one(Inspector).show_model(graph.selected, 0, len(graph.graph))


def main() -> None:
    app = ModelNavigatorApp()
    app.run()
