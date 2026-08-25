# This module contains constant-evaluation versions of the Krita Selection nodes.
from ...util.krita import Selection, Bounds
from . import ConstantNode, InputValue, function


@function(
    name="Krita Selection",
    inputs_constant=True,
    outputs=2,
)
class KritaSelection(ConstantNode):
    def run(self):
        if self.workflow.cached_selection is None:
            bounds = self.workflow.bounds()

            selection = self.workflow.document.selection()

            if selection is None:
                selection = Selection.solid(bounds, 0xff)
                active = False

            else:
                if selection.bounds() == bounds:
                    # TODO figure out a faster way of determining if the selection is fully white
                    active = not selection.mask(bounds).is_solid(0xff)
                else:
                    active = True

            self.workflow.cached_selection = (selection, active)

        return self.workflow.cached_selection


@function(
    name="Krita Selection: Border",
    inputs_constant=True,
)
class KritaSelectionBorder(ConstantNode):
    def run(self, selection, x, y, mode):
        if x == 0 and y == 0:
            return selection

        elif mode == "outside":
            new_selection = selection.copy()
            new_selection.border_outside(x, y)
            return new_selection

        elif mode == "inside":
            new_selection = selection.copy()
            new_selection.border_inside(x, y)
            return new_selection

        elif mode == "both":
            new_selection = selection.copy()
            new_selection.border_both(x, y)
            return new_selection

        else:
            self.error("mode must outside, inside, or both")


@function(
    name="Krita Selection: Bounds",
    inputs_constant=True,
    outputs=4,
)
class KritaSelectionBounds(ConstantNode):
    def run(self, selection, round_up):
        document_bounds = self.workflow.bounds()

        bounds = selection.bounds()

        # Crops the selection to be within the document bounds
        if not bounds.is_within_bounds(document_bounds):
            selection = selection.copy()
            # TODO this is expensive
            selection.intersect(Selection.solid(document_bounds, 0xFF))
            bounds = selection.bounds()

        bounds = bounds.round_up(document_bounds, round_up)

        return (
            bounds.x,
            bounds.y,
            bounds.width,
            bounds.height,
        )


@function(
    name="Krita Selection: Feather",
    inputs_constant=True,
)
class KritaSelectionFeather(ConstantNode):
    def run(self, selection, amount, mode):
        if amount == 0:
            return selection

        elif mode == "outside":
            new_selection = selection.copy()
            new_selection.feather_outside(amount)

            # This guarantees that the original selection will always be
            # white. This prevents the feathering from bleeding into the
            # original selection.
            new_selection.add(selection)
            return new_selection

        elif mode == "inside":
            new_selection = selection.copy()
            new_selection.feather_inside(amount)
            return new_selection

        elif mode == "both":
            new_selection = selection.copy()
            new_selection.feather_both(amount)
            return new_selection

        else:
            raise self.error("mode must be outside, inside, or both")


@function(
    name="Krita Selection: Grow",
    inputs_constant=True,
)
class KritaSelectionGrow(ConstantNode):
    def run(self, selection, x, y):
        if x != 0 or y != 0:
            selection = selection.copy()
            selection.grow(x, y)

        return selection


@function(
    name="Krita Selection: Invert",
    inputs_constant=True,
)
class KritaSelectionInvert(ConstantNode):
    def run(self, selection):
        selection = selection.copy()
        selection.invert()
        return selection


@function(
    name="Krita Selection: Mask",
    inputs_constant=True,
    inputs={
        "crop": InputValue(optional=True),
    },
)
class KritaSelectionMask(ConstantNode):
    def run(self, selection, crop):
        if crop is None:
            crop = self.workflow.bounds()
        else:
            crop = Bounds.from_json(crop)

        mask = selection.mask(crop)
        return self.graph.mask(mask)


@function(
    name="Krita Selection: Shrink",
    inputs_constant=True,
)
class KritaSelectionShrink(ConstantNode):
    def run(self, selection, x, y):
        if x != 0 or y != 0:
            selection = selection.copy()
            selection.shrink(x, y)

        return selection


@function(
    name="Krita Selection: Smooth",
    inputs_constant=True,
)
class KritaSelectionSmooth(ConstantNode):
    def run(self, selection):
        selection = selection.copy()
        selection.smooth()
        return selection


CONST_NODES = {
    "krita_comfyui: KritaSelection": KritaSelection,
    "krita_comfyui: KritaSelectionBorder": KritaSelectionBorder,
    "krita_comfyui: KritaSelectionBounds": KritaSelectionBounds,
    "krita_comfyui: KritaSelectionFeather": KritaSelectionFeather,
    "krita_comfyui: KritaSelectionGrow": KritaSelectionGrow,
    "krita_comfyui: KritaSelectionInvert": KritaSelectionInvert,
    "krita_comfyui: KritaSelectionMask": KritaSelectionMask,
    "krita_comfyui: KritaSelectionShrink": KritaSelectionShrink,
    "krita_comfyui: KritaSelectionSmooth": KritaSelectionSmooth,
}
