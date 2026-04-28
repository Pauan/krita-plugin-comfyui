import json


def log_debug_json(value):
    with open("/tmp/krita.log", "a") as file:
        json.dump(value, file, indent=2)
        file.write("\n\n")
