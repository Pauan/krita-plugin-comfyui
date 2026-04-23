import math


# https://stackoverflow.com/a/2189827/449477
def digits(num):
    if num == 0:
        return 1
    else:
        return int(math.log10(num)) + 1


class Node:
    def __init__(self, id):
        self.id = id

    def out(self, index):
        return [self.id, index]


class Graph:
    def __init__(self):
        self.node_id = 0
        self.nodes = {}


    def node(self, name, **kwargs):
        id = str(self.node_id)
        self.node_id += 1

        self.nodes[id] = {
            "class_type": name,
            "inputs": kwargs,
        }

        return Node(id)


    def list(self, items):
        inputs = {}

        # We pad the numbers so that they are sorted correctly
        padding = digits(max(0, len(items) - 1))

        for i, value in enumerate(items):
            inputs["inputs.input" + str(i).zfill(padding)] = value

        return self.node("CreateList", **inputs).out(0)


    def serialize(self):
        print(self.nodes)
        return self.nodes
