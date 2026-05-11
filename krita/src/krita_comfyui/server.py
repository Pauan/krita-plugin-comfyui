import json
import uuid
from enum import Enum, auto
from . import util

from PyQt6.QtCore import QObject, QTimer, QUrl, QByteArray, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class GraphError:
    def __init__(self):
        super()
        self.message = ""
        self.node_id = None
        self.node_name = None
        self.backtrace = None


    def format(self):
        message = []

        if self.node_name is not None:
            message.append("[")
            message.append(self.node_name)
            message.append("]")

        if len(message) > 0:
            message.append("\n")

        message.append(self.message)

        return "".join(message)


    @staticmethod
    def from_execution_error(info):
        error = GraphError()

        node_name = info["node_type"]

        if node_name != "krita_comfyui: ThrowError":
            error.node_id = info["node_id"]
            error.node_name = node_name

        error.message = info["exception_message"]
        error.backtrace = "".join(info["traceback"])
        return error


    @staticmethod
    def from_comfyui_error(info):
        error = GraphError()

        output = []

        print(json.dumps(info, indent=2))

        message = info["error"]["message"]
        details = info["error"]["details"]

        if details == "":
            output.append(message)
        else:
            output.append(f"{message} ({details})")

        for value in info["node_errors"].values():
            class_type = value["class_type"]

            for info in value["errors"]:
                message = info["message"]
                details = info["details"]

                if details == "":
                    output.append(f"    [{class_type}] {message}")
                else:
                    output.append(f"    [{class_type}] {message} ({details})")

        error.message = "\n".join(output)
        return error


    @staticmethod
    def from_string(string):
        error = GraphError()
        error.message = string
        return error


class GraphState(Enum):
    Idle = auto()
    Sent = auto()
    Executing = auto()
    Done = auto()
    Error = auto()
    Cancelled = auto()

    def is_idle(self):
        return self == GraphState.Idle

    def is_running(self):
        return self == GraphState.Sent or self == GraphState.Executing

    def is_ended(self):
        return self == GraphState.Done or self == GraphState.Error or self == GraphState.Cancelled

    def is_success(self):
        return self == GraphState.Done

    def is_error(self):
        return self == GraphState.Error

    def button_icon(self):
        if self == GraphState.Idle:
            return Krita.icon("media-playback-start")
        elif self == GraphState.Sent or self == GraphState.Executing:
            return Krita.icon("media-record")
        elif self == GraphState.Cancelled:
            return Krita.icon("dialog-cancel")
        elif self == GraphState.Error:
            return Krita.icon("warning")
        else:
            return Krita.icon("dialog-ok")

    def status_icon(self):
        if self == GraphState.Idle:
            return Krita.icon("animation_pause")
        elif self == GraphState.Sent or GraphState.Executing:
            return Krita.icon("media-record")
        elif self == GraphState.Cancelled:
            return Krita.icon("dialog-cancel")
        elif self == GraphState.Error:
            return Krita.icon("warning")
        else:
            return Krita.icon("dialog-ok")


class GraphInfo:
    def __init__(self, graph_id, progress, state, error, outputs):
        self.graph_id = graph_id
        self.progress = progress
        self.state = state
        self.error = error
        self.outputs = outputs


class ProgressPercent:
    # The progress is based on a weighted average of all the nodes.
    #
    # Sample nodes (e.g. KSampler) take a lot longer than normal nodes.
    #
    # Normal nodes usually execute instantly, so we ignore them for
    # the progress bar.
    SAMPLE_WEIGHT = 1.0
    NORMAL_WEIGHT = 0.0

    def __init__(self):
        self.value = 0.0
        self.max = 1.0
        self.is_sample = False


    def update(self, value, max):
        # TODO figure out why some nodes like KritaOutput have an integer value of 1
        is_sample = isinstance(max, int) and max > 1

        changed = (self.value != value or self.max != max or self.is_sample != is_sample)
        self.value = value
        self.max = max
        self.is_sample = is_sample
        return changed


    def percent(self):
        if self.value == self.max:
            return 1.0
        else:
            return float(self.value) / float(self.max)


    def weight(self):
        if self.is_sample:
            return ProgressPercent.SAMPLE_WEIGHT
        else:
            return ProgressPercent.NORMAL_WEIGHT


class PromptProgress:
    def __init__(self, nodes):
        self.nodes = {}

        for id in nodes.keys():
            self.nodes[id] = ProgressPercent()


    def update(self, id, value, max):
        node = self.nodes.get(id, None)

        if node is None:
            node = ProgressPercent()
            self.nodes[id] = node

        return node.update(value, max)


    def update_done(self, id):
        node = self.nodes[id]
        return node.update(node.max, node.max)


    def percent(self):
        percent = 0.0
        total_percent = 0.0

        for node in self.nodes.values():
            weight = node.weight()
            percent += (node.percent() * weight)
            total_percent += weight

        if total_percent == 0.0:
            return 0.0
        else:
            return percent / total_percent


class Prompt:
    def __init__(self, client_id, graph_id, graph):
        self.client_id = client_id
        self.graph_id = graph_id
        self.graph = graph
        self.error = None
        self.outputs = []

        serialized = graph.serialize()

        self.progress = PromptProgress(serialized)

        self.prompt_id = str(uuid.uuid4())

        self.state = GraphState.Idle

        self.body = json.dumps({
            "client_id": self.client_id,
            "prompt_id": self.prompt_id,
            "prompt": serialized,
        }).encode("utf-8")


    def cancel(self):
        self.state = GraphState.Cancelled
        self.outputs = []


    def set_error(self, error):
        self.state = GraphState.Error
        self.error = error
        self.outputs = []


    def graph_info(self):
        if self.state.is_ended():
            progress = 1.0
        else:
            progress = self.progress.percent()

        return GraphInfo(self.graph_id, progress, self.state, self.error, self.outputs.copy())


    # Returns a fresh Prompt with the same graph.
    # This is needed for retrying the Prompt in the case of a disconnection.
    def copy(self):
        return Prompt(self.client_id, self.graph_id, self.graph)


class ConnectState(Enum):
    Disconnected = auto()
    Connecting = auto()
    Connected = auto()

class WebsocketClient(QObject):
    messages = pyqtSignal(dict)
    state_changed = pyqtSignal(ConnectState)

    def __init__(self, parent, url, reconnect_delay):
        super().__init__(parent)

        self.state = ConnectState.Disconnected
        self.should_connect = False

        self.url = url
        self.reconnect_delay = reconnect_delay

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._open_connection)

        self.client = QWebSocket(url)
        self.client.error.connect(self.on_error)
        self.client.textMessageReceived.connect(self.on_text_message)
        self.client.connected.connect(self.on_connected)
        self.client.disconnected.connect(self.on_disconnected)

    def _change_state(self, state):
        if self.state != state:
            self.state = state
            self.state_changed.emit(self.state)

    # WebSocket is connected and active
    def is_ready(self):
        return self.should_connect and self.state == ConnectState.Connected

    def _open_connection(self):
        if self.should_connect and self.state == ConnectState.Disconnected:
            self.client.open(QUrl(self.url))
            self._change_state(ConnectState.Connecting)

    def connect(self):
        if not self.should_connect:
            self.should_connect = True
            self._open_connection()

    def disconnect(self):
        if self.should_connect:
            self.should_connect = False
            self.timer.stop()
            self.client.close()
            self._change_state(ConnectState.Disconnected)

    def on_connected(self):
        if self.should_connect:
            assert self.state != ConnectState.Connected
            self._change_state(ConnectState.Connected)
        else:
            assert self.state == ConnectState.Disconnected

    def on_disconnected(self):
        if self.should_connect:
            self.timer.start(self.reconnect_delay)
        self._change_state(ConnectState.Disconnected)

    def on_error(self, error_code):
        print(f"WebSocket Error: {self.client.errorString()}")

    def on_text_message(self, message):
        if self.is_ready():
            self.messages.emit(json.loads(message))


class ComfyUIClient(QObject):
    graph_changed = pyqtSignal(GraphInfo)
    connection_changed = pyqtSignal()


    def __init__(self, parent, settings, url, reconnect_delay):
        super().__init__(parent)

        self.client_id = str(uuid.uuid4())
        self.graph_id = 0

        self.settings = settings
        self.url = url
        self.queue = []
        self.is_connected = False

        self.http = QNetworkAccessManager(self)
        self.http.setAutoDeleteReplies(True)
        self.http.finished.connect(self.on_http_finished)

        self.websocket = WebsocketClient(self, f"ws://{self.url}/ws?clientId={self.client_id}", reconnect_delay)
        self.websocket.messages.connect(self.on_websocket_message)
        self.websocket.state_changed.connect(self.on_websocket_state_changed)


    def find_prompt(self, prompt_id):
        for prompt in self.queue:
            if prompt.prompt_id == prompt_id:
                return prompt


    def post_prompt(self, prompt):
        if self.websocket.is_ready():
            url = f"http://{self.url}/prompt"
            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            request.setAttribute(QNetworkRequest.Attribute.User, "prompt")
            request.setAttribute(QNetworkRequest.Attribute(QNetworkRequest.Attribute.User.value + 1), prompt.prompt_id)
            self.http.post(request, QByteArray(prompt.body))


    def interrupt_prompt(self, prompt):
        if self.websocket.is_ready():
            url = f"http://{self.url}/interrupt"

            message = {
                "prompt_id": prompt.prompt_id,
            }

            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            request.setAttribute(QNetworkRequest.Attribute.User, "interrupt")
            self.http.post(request, QByteArray(json.dumps(message).encode("utf-8")))


    def execute_queue(self):
        # We only send HTTP requests when the WebSocket server is connected.
        #
        # If it's not connected, it will automatically call execute_queue
        # when it connects.
        if self.websocket.is_ready() and len(self.queue) > 0:
            prompt = self.queue[0]

            # Don't send the same prompt multiple times
            if prompt.state.is_idle():
                self.post_prompt(prompt)
                prompt.state = GraphState.Sent

                self.graph_changed.emit(prompt.graph_info())


    def on_websocket_state_changed(self, state):
        if state == ConnectState.Disconnected:
            # When the WebSocket disconnects, we assume that the entire ComfyUI server
            # has died, so we assume that in-progress prompts will never finish,
            # so we reset all of the prompts in the queue.
            #
            # When the WebSocket reconnects, it will automatically re-run the prompts
            # in the queue.
            new_queue = []

            for prompt in self.queue:
                prompt.cancel()
                new_queue.append(prompt.copy())

            self.queue = new_queue

            for prompt in self.queue:
                self.graph_changed.emit(prompt.graph_info())

        elif state == ConnectState.Connected:
            self.update_node_metadata()
            self.execute_queue()

        self.update_is_connected()


    def on_prompt_executing(self, prompt_id):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            prompt.state = GraphState.Executing
            self.graph_changed.emit(prompt.graph_info())


    def on_execution_cached(self, prompt_id, nodes):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            changed = False

            # These nodes have been cached, so they won't be re-executed.
            # But we still need to count them toward the total progress.
            for id in nodes:
                if prompt.progress.update_done(id):
                    changed = True

            if changed:
                self.graph_changed.emit(prompt.graph_info())


    def on_prompt_progress(self, prompt_id, nodes):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            changed = False

            for node in nodes.values():
                parent = node["parent_node_id"]

                # If a node has a parent, then that means the parent was
                # replaced with a sub-graph of nodes.
                #
                # Since the parent was replaced, it has already been finished,
                # so we mark it as done.
                if parent is not None:
                    if prompt.progress.update_done(parent):
                        changed = True

                if prompt.progress.update(node["node_id"], node["value"], node["max"]):
                    changed = True

            if changed:
                self.graph_changed.emit(prompt.graph_info())


    def on_prompt_executed(self, prompt_id, output):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            prompt.outputs.append(output)
            self.graph_changed.emit(prompt.graph_info())


    def on_prompt_finished(self, prompt_id):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            prompt.state = GraphState.Done
            self.queue.remove(prompt)
            self.graph_changed.emit(prompt.graph_info())
            self.execute_queue()


    def on_prompt_error(self, prompt_id, info):
        prompt = self.find_prompt(prompt_id)

        # If the prompt hasn't been reset...
        if prompt is not None and prompt.state.is_running():
            prompt.set_error(GraphError.from_execution_error(info))
            self.queue.remove(prompt)
            self.graph_changed.emit(prompt.graph_info())
            self.execute_queue()


    def on_websocket_message(self, message):
        #util.log_debug_json(message)

        if message["type"] == "execution_start":
            self.on_prompt_executing(message["data"]["prompt_id"])

        elif message["type"] == "execution_cached":
            data = message["data"]
            self.on_execution_cached(data["prompt_id"], data["nodes"])

        elif message["type"] == "progress_state":
            data = message["data"]
            self.on_prompt_progress(data["prompt_id"], data["nodes"])

        elif message["type"] == "executed":
            data = message["data"]
            output = data.get("output", None)

            if output is not None:
                self.on_prompt_executed(data["prompt_id"], output)

        elif message["type"] == "execution_success":
            self.on_prompt_finished(message["data"]["prompt_id"])

        elif message["type"] == "execution_error":
            data = message["data"]
            self.on_prompt_error(data["prompt_id"], data)


    def on_http_finished(self, reply):
        error = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)

        if status is None:
            error = GraphError.from_string(reply.errorString())

        # Prompt was bad, display ComfyUI error message
        elif status == 400:
            error = GraphError.from_comfyui_error(json.loads(reply.readAll().data().decode("utf-8")))

        # Other major network error happened
        elif not (status >= 200 and status < 300):
            error = GraphError.from_string(reply.errorString())

        # Everything was fine!
        else:
            assert reply.error() == QNetworkReply.NetworkError.NoError

        if error is not None:
            print(f"HTTP Error: {error.format()}")

        match reply.request().attribute(QNetworkRequest.Attribute.User):
            case "prompt":
                if error is not None:
                    prompt_id = reply.request().attribute(QNetworkRequest.Attribute(QNetworkRequest.Attribute.User.value + 1))

                    assert prompt_id is not None

                    prompt = self.find_prompt(prompt_id)

                    # If the prompt hasn't been reset...
                    if prompt is not None and not prompt.state.is_ended():
                        prompt.set_error(error)
                        self.queue.remove(prompt)
                        self.graph_changed.emit(prompt.graph_info())
                        self.execute_queue()

            case "interrupt":
                pass

            case "object_info":
                if error is None:
                    node_metadata = json.loads(reply.readAll().data().decode("utf-8"))
                    self.settings.save_node_metadata(node_metadata)

        reply.deleteLater()


    def update_is_connected(self):
        is_ready = self.websocket.is_ready()

        if self.is_connected != is_ready:
            self.is_connected = is_ready
            self.connection_changed.emit()


    def connect(self):
        self.websocket.connect()
        self.execute_queue()
        self.update_is_connected()


    def disconnect(self):
        self.websocket.disconnect()
        self.update_is_connected()


    # Stop executing a specific graph
    def stop_execute_graph(self, graph_id):
        remove = [prompt for prompt in self.queue if prompt.graph_id == graph_id]

        for prompt in remove:
            is_running = prompt.state.is_running()

            prompt.cancel()
            self.queue.remove(prompt)
            self.graph_changed.emit(prompt.graph_info())

            if is_running:
                self.interrupt_prompt(prompt)

        self.execute_queue()


    # Removes pending prompts which haven't been sent yet
    def clear_queue_pending(self):
        remove = [prompt for prompt in self.queue if prompt.state.is_idle()]

        for prompt in remove:
            prompt.cancel()
            self.queue.remove(prompt)
            self.graph_changed.emit(prompt.graph_info())

        self.execute_queue()


    # Removes all prompts, including prompts that are in progress
    def clear_queue(self):
        if len(self.queue) > 0:
            old = self.queue

            self.queue = []

            for prompt in old:
                is_running = prompt.state.is_running()

                prompt.cancel()
                self.graph_changed.emit(prompt.graph_info())

                if is_running:
                    self.interrupt_prompt(prompt)


    def current_queue(self):
        return [prompt.graph_info() for prompt in self.queue]


    def update_node_metadata(self):
        if self.websocket.is_ready():
            request = QNetworkRequest(QUrl(f"http://{self.url}/object_info"))
            request.setAttribute(QNetworkRequest.Attribute.User, "object_info")
            self.http.get(request)


    def execute_graph(self, graph):
        util.log_debug_json(graph.debug())

        graph_id = str(self.graph_id)

        self.graph_id += 1

        prompt = Prompt(self.client_id, graph_id, graph)

        self.queue.append(prompt)

        graph_info = prompt.graph_info()

        self.graph_changed.emit(graph_info)

        self.execute_queue()

        return graph_info
