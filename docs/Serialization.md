# Inputs

Workflow UI inputs are serialized into JSON and stored in the `.kra` document.

The inputs are stored in the `krita_comfyui/ui_inputs/{UUID}` key, where `{UUID}` is the unique ID of the workflow.

## The format of the JSON

The JSON is a `{ ... }` object where each key is the type + ID of a UI widget.

For example, an integer widget with the id `foo` will have the key `int/foo`, a float widget will have the key `float/foo`, etc.

The value of each key is the value of the UI widget.

If a key does not exist, then the widget will use the default value (which can be set in the workflow).

### Groups

Groups store a boolean for whether they are open or closed.

### Lists

Lists store an array of objects, one object per element in the list.

Each object follows the same format as above: the keys are the type + ID of the widget, and the value is the value of the widget.

It is possible to have lists nested within lists, each nested list contains its own array of children.

# Outputs

## Images

Output images are stored in the `.kra` document.

Each image is given a unique UUID, and has additional metadata such as its x, y, width, height, and name.

The image metadata is stored in `krita_comfyui/image_metadata/{UUID}` where `{UUID}` is the unique ID of the image.

The image bytes is stored in `krita_comfyui/image_bytes/{UUID}` where `{UUID}` is the unique ID of the image.

A list of image UUIDs is stored in `krita_comfyui/image_uuids`

## Text

Output text is stored in the `krita_comfyui/output_texts` key.
