from . import WorkflowError, Link, zip_inputs, check_booleans


class UiLink(Link):
    def __init__(self, values, ids):
        super().__init__(values)
        self.ids = ids


# Evaluates a UI widget to a constant value
class KritaUi:
    def __init__(self, type):
        self.type = type

    def get_id(self, id):
        return f"{self.type}/{id}"

    def get_outputs(self, workflow, node_id, node):
        ids = []
        outputs = []
        is_default = []

        for id in workflow.evaluate_link(node["inputs"]["id"]).values:
            id = self.get_id(id)
            values = workflow.get_ui_values(id)
            default = workflow.defaults[id]

            ids.append(id)
            outputs.extend(values)
            is_default.extend(value == default for value in values)

        return (
            UiLink(outputs, ids),
            UiLink(is_default, ids),
        )


class KritaCanvas:
    def __init__(self):
        self.canvas = None

    def get_outputs(self, workflow, node_id, node):
        if self.canvas is None:
            bounds = workflow.bounds()

            image = workflow.document.canvas(bounds)

            (image, mask) = workflow.graph.image(image)

            self.canvas = (
                Link([image]),
                Link([mask]),
                Link([bounds.width]),
                Link([bounds.height]),
            )

        return self.canvas


class KritaDebug:
    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        enabled = workflow.evaluate_link(inputs["enabled"])

        (all_true, all_false) = check_booleans(enabled.values)

        # If it's disabled, don't evaluate anything.
        if all_false and not all_true:
            return ()

        else:
            outputs = {}

            for key, value in inputs.items():
                if key == "enabled":
                    outputs[key] = enabled.to_node(workflow.graph)
                else:
                    outputs[key] = workflow.evaluate_link(value).to_node(workflow.graph)

            workflow.graph.node("krita_comfyui: KritaDebug", **outputs)

            return ()


class KritaLayers:
    def __init__(self):
        self.layers = {}
        self.layer_image = {}


    def get_layer_image(self, workflow, layer):
        image = self.layer_image.get(layer.id, None)

        if image is None:
            image = workflow.graph.image(layer.image(workflow.bounds()))
            self.layer_image[layer.id] = image

        return image


    def get_layers(self, workflow, layer_id, mode):
        layers = self.layers.get((layer_id, mode), None)

        if layers is None:
            images = []
            masks = []
            names = []

            layer = workflow.document.find_layer_by_id(layer_id)

            if layer is None:
                raise WorkflowError(f"Could not find layer {layer_id}")

            def add_image(layer):
                (image, mask) = self.get_layer_image(workflow, layer)
                images.append(image)
                masks.append(mask)
                names.append(layer.name)

            if mode == "individual":
                if layer.type.is_image():
                    add_image(layer)

                for child in layer.all_children():
                    if child.type.is_image():
                        add_image(child)

            elif mode == "flatten":
                if layer.type.is_image() or layer.type.is_group():
                    add_image(layer)

            else:
                raise WorkflowError("mode must be individual or flatten")

            layers = (images, masks, names)
            self.layers[(layer_id, mode)] = layers

        return layers


    def get_outputs(self, workflow, node_id, node):
        inputs = node["inputs"]

        images = []
        masks = []
        names = []

        layer_id_link = workflow.evaluate_link(inputs["layer_id"])
        mode_link = workflow.evaluate_link(inputs["mode"])

        error = None

        for (layer_id, mode) in zip_inputs(layer_id_link, mode_link):
            if not isinstance(layer_id, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nlayer_id must be a string constant")

            if not isinstance(mode, str):
                raise WorkflowError(f"[#{node_id} Krita Layers]\nmode must be a string constant")

            # If the layer name is empty, throw an error
            if layer_id == "":
                if error is None:
                    # TODO maybe raise the error immediately?
                    if isinstance(layer_id_link, UiLink):
                        error = workflow.graph.error(f"Layer selector [{", ".join(layer_id_link.ids)}] is empty")
                    else:
                        error = workflow.graph.error(f"[#{node_id} Krita Layers]\nlayer_id is empty")

                images.append(error)
                masks.append(error)
                names.append(error)

            else:
                layers = self.get_layers(workflow, layer_id, mode)
                images.extend(layers[0])
                masks.extend(layers[1])
                names.extend(layers[2])

        return (
            Link(images),
            Link(masks),
            Link(names),
        )


class KritaSeed:
    def get_outputs(self, workflow, node_id, node):
        return (
            Link([workflow.seed]),
        )
