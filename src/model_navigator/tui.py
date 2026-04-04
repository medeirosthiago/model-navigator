from model_navigator.lineage import assign_columns, nodes_with_depth
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
    depth = reactive(2, recompose=True)

    def __init__(self, graph: dict, selected: str):
        super().__init__(id="graph")
        self.graph = graph
        self.selected = selected

    def visible_nodes(self) -> set[str]:
        return nodes_with_depth(self.graph, self.selected, self.depth)

    def compose(self) -> ComposeResult:
        columns = assign_columns(self.graph)
        visible = self.visible_nodes()
        grouped: dict[int, list[str]] = {}
        for name, col in columns.items():
            if name in visible:
                grouped.setdefault(col, []).append(name)

        with Horizontal(id="columns"):
            for col_idx in sorted(grouped):
                with Vertical(classes="graph-column"):
                    for name in sorted(grouped[col_idx]):
                        classes = (
                            "node-box selected" if name == self.selected else "node-box"
                        )
                        yield Static(name, classes=classes)


class Inspector(Static):
    @staticmethod
    def _format_relations(names: list[str]) -> Text:
        if not names:
            return Text("none", style="dim")
        return Text("\n".join(f"- {name}" for name in names), style="dim")

    def show_model(self, graph: dict, name: str, depth: int):
        node = graph[name]
        columns = assign_columns(graph)
        visible = nodes_with_depth(graph, name, depth)
        title = Text(name, style="bold")

        details = Table.grid(padding=(0, 1))
        details.add_column(style="bold", width=10)
        details.add_column()
        details.add_row("Type", str(node.get("type", "model")))
        details.add_row("Package", "my_project")
        details.add_row("Column", str(columns[name]))
        details.add_row("Depth", str(depth))
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

    #columns {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    .graph-column {
        width: auto;
        height: auto;
        align: center middle;
    }

    .node-box {
        width: 24;
        height: 3;
        content-align: center middle;
        border: round $surface-lighten-2;
        background: $panel;
        margin: 1;
    }

    .node-box.selected {
        border: round $accent;
        background: $boost;
        text-style: bold;
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
        self.notify(f"Depth: {graph.depth}")
        self._refresh_selection()

    def action_increase_depth(self):
        graph = self.query_one(LineageGraph)
        max_depth = len(graph.graph) - 1
        if graph.depth >= max_depth:
            return
        graph.depth += 1
        self.notify(f"Depth: {graph.depth}")
        self._refresh_selection()

    def _refresh_selection(self):
        graph = self.query_one(LineageGraph)
        self.sub_title = f"{graph.selected} | depth {graph.depth}"
        self.query_one(Inspector).show_model(graph.graph, graph.selected, graph.depth)


def main() -> None:
    app = ModelNavigatorApp()
    app.run()
