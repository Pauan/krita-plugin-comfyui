import os
import json


def clear_logs():
    # Deletes the log file
    with open("/tmp/krita.log", "w") as file:
        pass
    #try:
        #os.remove("/tmp/krita.log")
    #except:
        #pass


def log_debug_json(value):
    with open("/tmp/krita.log", "a") as file:
        json.dump(value, file, indent=2)
        file.write("\n\n")
