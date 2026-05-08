from ...util.krita import Selection
from . import WorkflowError, Link, zip_inputs


class KritaSelection:
    def __init__(self):
        self.selection = None

    def get_outputs(self, workflow, node_id, node):
        if self.selection is None:
            bounds = workflow.bounds()

            selection = workflow.document.selection()

            if selection is None:
                selection = Selection.solid(bounds, 0xff)
                active = False

            else:
                if selection.bounds() == bounds:
                    # TODO figure out a faster way of determining if the selection is fully white
                    active = not selection.mask(bounds).is_solid(0xff)
                else:
                    active = True

            self.selection = (
                Link([selection]),
                Link([active]),
            )

        return self.selection


class KritaSelectionBorder:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])
        mode = workflow.evaluate_link(inputs["mode"])

        outputs = []

        for selection, x, y, mode in zip_inputs(selection, x, y, mode):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Border]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Border]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            elif mode == "outside":
                new_selection = selection.copy()
                new_selection.border_outside(x, y)
                outputs.append(new_selection)

            elif mode == "inside":
                new_selection = selection.copy()
                new_selection.border_inside(x, y)
                outputs.append(new_selection)

            elif mode == "both":
                new_selection = selection.copy()
                new_selection.border_both(x, y)
                outputs.append(new_selection)

            else:
                raise WorkflowError(f"[#{node_id} Krita Selection: Border]\nmode must outside, inside, or both")

        return (
            Link(outputs),
        )


class KritaSelectionBounds:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        round_up = workflow.evaluate_link(inputs["round_up"])

        x = []
        y = []
        width = []
        height = []

        for selection, round_up in zip_inputs(selection, round_up):
            assert isinstance(selection, Selection)
            bounds = selection.bounds().round_up(workflow.bounds(), round_up)
            x.append(bounds.x)
            y.append(bounds.y)
            width.append(bounds.width)
            height.append(bounds.height)

        return (
            Link(x),
            Link(y),
            Link(width),
            Link(height),
        )


class KritaSelectionFeather:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        amount = workflow.evaluate_link(inputs["amount"])
        mode = workflow.evaluate_link(inputs["mode"])

        outputs = []

        for selection, amount, mode in zip_inputs(selection, amount, mode):
            assert isinstance(selection, Selection)

            if not isinstance(amount, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\namount must be an int constant")

            if not isinstance(mode, str):
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\nmode must be a string constant")

            if amount == 0:
                outputs.append(selection)

            elif mode == "outside":
                new_selection = selection.copy()
                new_selection.feather_outside(amount)

                # This guarantees that the original selection will always be
                # white. This prevents the feathering from bleeding into the
                # original selection.
                new_selection.add(selection)
                outputs.append(new_selection)

            elif mode == "inside":
                new_selection = selection.copy()
                new_selection.feather_inside(amount)
                outputs.append(new_selection)

            elif mode == "both":
                new_selection = selection.copy()
                new_selection.feather_both(amount)
                outputs.append(new_selection)

            else:
                raise WorkflowError(f"[#{node_id} Krita Selection: Feather]\nmode must outside, inside, or both")

        return (
            Link(outputs),
        )


class KritaSelectionGrow:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])

        outputs = []

        for selection, x, y in zip_inputs(selection, x, y):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Grow]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Grow]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            else:
                selection = selection.copy()
                selection.grow(x, y)
                outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionInvert:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            selection = selection.copy()
            selection.invert()
            outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionMask:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            mask = selection.mask(workflow.bounds())
            mask = workflow.graph.mask(mask)
            outputs.append(mask)

        return (
            Link(outputs),
        )


class KritaSelectionShrink:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])
        x = workflow.evaluate_link(inputs["x"])
        y = workflow.evaluate_link(inputs["y"])

        outputs = []

        for selection, x, y in zip_inputs(selection, x, y):
            assert isinstance(selection, Selection)

            if not isinstance(x, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Shrink]\nx must be an int constant")

            if not isinstance(y, int):
                raise WorkflowError(f"[#{node_id} Krita Selection: Shrink]\ny must be an int constant")

            if x == 0 and y == 0:
                outputs.append(selection)

            else:
                selection = selection.copy()
                selection.shrink(x, y)
                outputs.append(selection)

        return (
            Link(outputs),
        )


class KritaSelectionSmooth:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        selection = workflow.evaluate_link(inputs["selection"])

        outputs = []

        for selection in selection.values:
            assert isinstance(selection, Selection)
            selection = selection.copy()
            selection.smooth()
            outputs.append(selection)

        return (
            Link(outputs),
        )
