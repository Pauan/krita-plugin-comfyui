import os
import json
import time


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


class Perf:
    def __init__(self, name):
        self.name = name

    def done(self):
        end = time.perf_counter_ns()
        print("{} took {} ms".format(self.name, float(end - self.start) / 1000000.0))

    def __enter__(self):
        self.start = time.perf_counter_ns()

    async def __aenter__(self):
        self.start = time.perf_counter_ns()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.done()
        return False

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.done()
        return False
