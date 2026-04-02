from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Static
from textual.widget import Widget


class LineageGraph(Widget, can_focus=True):
    def __init__(self, models: list[str]):
        super().__init__(id="graph")
        self.models = models
        self.selected = 0

    def compose(self) -> ComposeResult:
        yield Static(self.models[self.selected], id="node-box")

    def select_prev(self):
        self.selected = max(self.selected - 1, 0)
        self.query_one("#node-box", Static).update(self.models[self.selected])

    def select_next(self):
        self.selected = min(self.selected + 1, len(self.models) - 1)
        self.query_one("#node-box", Static).update(self.models[self.selected])



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

        self.update(Group(
            title,
            Rule(style="dim"),
            details,
            Rule(title="Upstream", style="dim"),
            upstream,
            Rule(title="Downstream", style="dim"),
            downstream,
        ))


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

    #node-box {
        width: 24;
        height: 3;
        content-align: center middle;
        border: round $accent;
        background: $panel;
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

    FAKE_MODELS = ["stg_charges", "int_revenue", "fct_payments", "dim_customers", "stg_users"]

    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield LineageGraph(self.FAKE_MODELS)
            yield Inspector("Inspector", id="inspector")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Model Navigator"
        self._refresh_selection()

    def action_select_prev(self):
        graph = self.query_one(LineageGraph)
        graph.select_prev()
        self._refresh_selection()

    def action_select_next(self):
        graph = self.query_one(LineageGraph)
        graph.select_next()
        self._refresh_selection()

    def _refresh_selection(self):
        graph = self.query_one(LineageGraph)
        name = graph.models[graph.selected]
        self.sub_title = name
        self.query_one(Inspector).show_model(name, graph.selected, len(graph.models))


def main() -> None:
    app = ModelNavigatorApp()
    app.run()
