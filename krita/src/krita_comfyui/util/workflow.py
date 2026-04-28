class WorkflowInputs:
    def __init__(self, document, seed, ui_values):
        self.document = document
        self.seed = seed
        self.ui_values = ui_values


    def get_ui(self, id):
        try:
            return self.ui_values[id]
        except KeyError:
            raise RuntimeError("UI {} not found", id)


    def get_selection(self):
        bounds = self.document.bounds()

        selection = self.document.selection()

        if selection is not None:
            selection_bounds = selection.bounds().clamp_to_parent(bounds)
            mask = selection.mask(bounds)

            if selection_bounds == bounds:
                active = not mask.is_solid(0xff)
            else:
                active = True

        else:
            selection_bounds = bounds
            mask = Mask.solid(0xff, bounds.width, bounds.height)
            active = False

        return (
            active,
            mask,
            selection_bounds.x,
            selection_bounds.y,
            selection_bounds.width,
            selection_bounds.height,
        )


    def get_canvas(self):
        bounds = self.document.bounds()
        image = self.document.canvas(bounds)
        return (image, bounds.width, bounds.height)


    def get_layers(self, layer_name, mode):
        layers = []

        bounds = self.document.bounds()

        layer = self.document.find_layer_by_name(layer_name)

        if layer is None:
            raise RuntimeError("Could not find layer {}".format(layer_name))

        def add_image(layer):
            layers.append((layer.name, layer.image(bounds)))

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
            raise RuntimeError("mode must be individual or flatten")

        return layers


class Workflow:
    def __init__(self, json, inputs):
        self.json = json
        self.inputs = inputs

        self.graph = Graph()

        self.replaced_links = {}
        self.replaced_ids = {}

        self.canvas = None
        self.selected = None
        self.layers = {}

        self.const_nodes = {
            "krita_comfyui: KritaUiFloat": self.evaluate_ui,
            "krita_comfyui: KritaUiInt": self.evaluate_ui,
            "krita_comfyui: KritaUiBoolean": self.evaluate_ui,
            "krita_comfyui: KritaUiString": self.evaluate_ui,
            "krita_comfyui: KritaUiLayerName": self.evaluate_ui,
            "krita_comfyui: KritaUiCombo": self.evaluate_ui,
        }


    def replace_outputs(self, id, outputs):
        for index, output in enumerate(outputs):
            self.replaced_links[(id, index)] = output


    def replace_id(old_id, node):
        self.replaced_ids[old_id] = node.id


    def evaluate_ui(self, node):
        ui_id = node["inputs"]["id"]
        value = self.inputs.get_ui(ui_id)
        return (value, value != "")


    # Evaluates the link if the connected node has a constant value
    def evaluate_link(self, value):
        # If it's a node link, then follow the link.
        if isinstance(value, list) and len(value) == 2:
            node = self.json[value[0]]
            name = node["class_type"]

            try:
                f = self.const_nodes[name]
            except KeyError:
                # If the node isn't constant, return the link as-is
                return value

            outputs = f(node)

            return outputs[value[1]]

        else:
            return value


    def get_canvas(self):
        if self.canvas is None:
            (image, width, height) = self.inputs.get_canvas()
            (image, mask) = self.graph.image(image)
            self.canvas = (image, mask, width, height)

        return self.canvas


    def get_selection(self):
        if self.selection is None:
            (active, mask, x, y, width, height) = self.inputs.get_selection()
            mask = self.graph.mask(mask)
            self.selection = (active, mask, x, y, width, height)

        return self.selection


    def get_layers(self, layer_name, mode):
        layer = self.layers.get((layer_name, mode), None)

        if layer is None:
            images = []
            masks = []
            names = []

            for (name, image) in self.inputs.get_layers(layer_name, mode):
                (image, mask) = self.graph.image(image)
                images.append(image)
                masks.append(mask)
                names.append(name)

            layer = (
                self.graph.list(images),
                self.graph.list(masks),
                self.graph.list(names),
            )

            self.layers[(layer_name, mode)] = layer

        return layer


    def process_node(self, id, node):
        class_type = node["class_type"]

        match class_type:
            case "krita_comfyui: KritaCanvas":
                self.replace_outputs(id, self.get_canvas())


            case "krita_comfyui: KritaSeed":
                self.replace_outputs(id, (self.inputs.seed,))


            case "krita_comfyui: KritaLayers":
                inputs = node["inputs"]

                layer_name = self.evaluate_link(inputs["layer_name"])

                if not isinstance(layer_name, str):
                    raise RuntimeError("[#{} Krita Layers] layer_name must be a string constant".format(id))

                # If the layer name is empty, throw an error
                if layer_name == "":
                    error = self.graph.error("[#{} Krita Layers] layer_name is empty".format(id))

                    self.replace_outputs(id, (error, error, error))

                else:
                    mode = self.evaluate_link(inputs["mode"])

                    if not isinstance(mode, str):
                        raise RuntimeError("[#{} Krita Layers] mode must be a string constant".format(id))

                    self.replace_outputs(id, self.get_layers(layer_name, mode))


            case "krita_comfyui: KritaSelection":
                self.replace_outputs(id, self.get_selection())


            case _:
                self.replace_id(id, self.graph.node(class_type, **node["inputs"]))


    def replace_input(self, value):
        value = self.evaluate_link(value)

        if isinstance(value, list) and len(value) == 2:
            try:
                new_id = self.replaced_ids[value[0]]
                return [new_id, value[1]]
            except KeyError:
                pass

            try:
                return self.replaced_links[(value[0], value[1])]
            except KeyError:
                pass

        return value


    def serialize(self):
        for id, node in self.json.items():
            # We skip const nodes completely, they're evaluated by `evaluate_link`
            if not node["class_type"] in self.const_nodes:
                self.process_node(id, node)


        for node in self.graph.nodes.values():
            inputs = {}

            for key, value in node["inputs"].items():
                inputs[key] = self.replace_input(value)

            node["inputs"] = inputs


        return self.graph.serialize()
