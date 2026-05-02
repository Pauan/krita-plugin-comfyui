Workflow UI inputs are serialized into JSON and stored in the `.kra` document.

The inputs are stored in the `krita_comfyui/ui_inputs/{UUID}` key, where `{UUID}` is the unique ID of the workflow.

# The format of the JSON

It is a single flat `{ ... }` object where each key is the ID of a UI widget.

The value of each key is an array of values. Each value within the array is the value of a single widget.

Because of UI lists, there can be multiple widgets with the same ID, which is why it's an array of values.

Within the array, `None` means that it is the default value.

# Widgets

Each widget has an ID and index. The index is the index within the array.

If a widget has an index greater than the length of the array, it is implied to be `None` (the default value).

# Groups

Groups store a boolean for whether they are open or closed.

# Lists

Lists store the number of children that are within the list. The actual values of the children are stored within their respective ID arrays.

When a widget is a child of a list, the list allows for creating multiple of that widget.

The values of those multiple widgets are stored in the array, in the same order as in the list.

For nested lists, the order of the array is depth-first, and each list operates on a slice of the array.

For example, if you have this structure...

```
list1 [
    widget1 = 1
    widget1 = 5

    list2 [
        widget1 = 3
        widget1 = 0
        widget1 = 9
        widget1 = 4
    ]

    list3 [
        widget1 = 2
        widget1 = 6
    ]
]
```

All of the child widgets have the same ID (`widget1`), so the JSON will look like this:

```json
{
  "list1": [4],
  "list2": [4],
  "list3": [2],
  "widget1": [1, 5, 3, 0, 9, 4, 2, 6]
}
```

Each list stores the number of immediate children it has. All of the `widget1` values are stored in a flat array.

Each list operates on a subset of the `widget1` array:

* `list1` will operate on the indexes 0 to 1
* `list2` will operate on the indexes 2 to 5
* `list3` will operate on the indexes 6 to 7

So even though `widget1` is a flat array, it knows which elements belong to which list.
