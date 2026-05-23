import json
import uuid
from enum import Enum, auto
from . import util
from .settings import LogLevel

from PyQt6.QtCore import QObject, QTimer, QUrl, QUrlQuery, QByteArray, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class ComfyError:
    def __init__(self, info):
        self.main_error = None
        self.node_errors = []

        main_error = info.get("error", None)

        if main_error is not None:
            message = main_error["message"]
            details = main_error["details"]

            if details == "":
                self.main_error = message
            else:
                self.main_error = f"{message}\n{details}"

        node_errors = info.get("node_errors", None)

        if node_errors is not None:
            for value in node_errors.values():
                class_type = value["class_type"]

                for info in value["errors"]:
                    message = info["message"]
                    details = info["details"]

                    if details == "":
                        self.node_errors.append(f"[{class_type}] {message}")
                    else:
                        self.node_errors.append(f"[{class_type}] {message} ({details})")


    def has_errors(self):
        return self.main_error is not None or len(self.node_errors) > 0


    def to_string(self):
        output = []

        if self.main_error is not None:
            output.append(self.main_error)

        if len(output) > 0 and len(self.node_errors) > 0:
            output.append("")

        for error in self.node_errors:
            if self.main_error is None:
                output.append(error)
            else:
                output.append(f"    {error}")

        return "\n".join(output)


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
    def from_comfyui_error(comfy_error):
        error = GraphError()
        error.message = comfy_error.to_string()
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

    def status_text(self):
        match self:
            case GraphState.Idle: return "Pending"
            case GraphState.Sent | GraphState.Executing: return "Running"
            case GraphState.Cancelled: return "Cancelled"
            case GraphState.Error: return "Errored"
            case GraphState.Done: return "Finished"

    def button_icon(self):
        match self:
            case GraphState.Idle:
                return Krita.icon("media-playback-start")
            case GraphState.Sent | GraphState.Executing:
                return Krita.icon("media-record")
            case GraphState.Cancelled:
                return Krita.icon("dialog-cancel")
            case GraphState.Error:
                return Krita.icon("warning")
            case GraphState.Done:
                return Krita.icon("dialog-ok")

    def status_icon(self):
        match self:
            case GraphState.Idle:
                return Krita.icon("animation_pause")
            case GraphState.Sent | GraphState.Executing:
                return Krita.icon("media-record")
            case GraphState.Cancelled:
                return Krita.icon("dialog-cancel")
            case GraphState.Error:
                return Krita.icon("warning")
            case GraphState.Done:
                return Krita.icon("dialog-ok")


class GraphInfo:
    def __init__(self, document_id, graph_id, progress, state, error, outputs, is_live_mode, should_notify):
        self.document_id = document_id
        self.graph_id = graph_id
        self.progress = progress
        self.state = state
        self.error = error
        self.outputs = outputs
        self.is_live_mode = is_live_mode
        self.should_notify = should_notify


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
    def __init__(self, document_id, client_id, graph_id, graph, is_live_mode, should_notify):
        self.document_id = document_id
        self.client_id = client_id
        self.graph_id = graph_id
        self.graph = graph
        self.is_live_mode = is_live_mode
        self.should_notify = should_notify
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

        return GraphInfo(
            self.document_id,
            self.graph_id,
            progress,
            self.state,
            self.error,
            self.outputs.copy(),
            self.is_live_mode,
            self.should_notify,
        )


    # Returns a fresh Prompt with the same graph.
    # This is needed for retrying the Prompt in the case of a disconnection.
    def copy(self):
        return Prompt(self.document_id, self.client_id, self.graph_id, self.graph, self.is_live_mode, self.should_notify)


class ConnectState(Enum):
    Disconnected = auto()
    Connecting = auto()
    Connected = auto()

class WebsocketClient(QObject):
    messages = pyqtSignal(dict)
    error = pyqtSignal(str)
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
        self.error.emit(self.client.errorString())

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

        self.pending_danbooru_tags = None
        self.last_danbooru_id = None

        self.http = QNetworkAccessManager(self)
        self.http.setAutoDeleteReplies(True)
        self.http.finished.connect(self.on_http_finished)

        self.websocket = WebsocketClient(self, f"ws://{self.url}/ws?clientId={self.client_id}", reconnect_delay)
        self.websocket.messages.connect(self.on_websocket_message)
        self.websocket.error.connect(self.on_websocket_error)
        self.websocket.state_changed.connect(self.on_websocket_state_changed)


    def request(self, *, url, metadata, username=None, password=None, headers=[], query={}):
        url = QUrl(url)

        if username is not None:
            url.setUserName(username)

        if password is not None:
            url.setPassword(password)

        if len(query) > 0:
            queries = QUrlQuery()

            for key, value in query.items():
                if value is not None:
                    queries.addQueryItem(key, value)

            url.setQuery(queries)

        request = QNetworkRequest(url)

        for key, value in headers:
            request.setHeader(key, value)

        request.setAttribute(QNetworkRequest.Attribute.User, metadata)

        return request


    def find_prompt(self, prompt_id):
        for prompt in self.queue:
            if prompt.prompt_id == prompt_id:
                return prompt


    def post_prompt(self, prompt):
        if self.websocket.is_ready():
            request = self.request(
                url=f"http://{self.url}/prompt",
                headers=[
                    (QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"),
                ],
                metadata={
                    "type": "prompt",
                    "prompt_id": prompt.prompt_id,
                }
            )
            self.http.post(request, QByteArray(prompt.body))


    def interrupt_prompt(self, prompt):
        if self.websocket.is_ready():
            message = {
                "prompt_id": prompt.prompt_id,
            }

            request = self.request(
                url=f"http://{self.url}/interrupt",
                headers=[
                    (QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"),
                ],
                metadata={
                    "type": "interrupt",
                },
            )

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


    def on_websocket_error(self, message):
        self.settings.log_str(f"WebSocket Error: {message}", level=LogLevel.ERROR)


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
        self.settings.log_json(message, label="Websocket Message", level=LogLevel.TRACE)

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

        # Standard HTTP error
        if status is None or (not (status >= 200 and status < 300)):
            error = GraphError.from_string(reply.errorString())

        # Everything was fine!
        else:
            assert reply.error() == QNetworkReply.NetworkError.NoError

        if error is not None:
            self.settings.log_str(f"HTTP Error: {error.format()}", level=LogLevel.ERROR)

        metadata = reply.request().attribute(QNetworkRequest.Attribute.User)

        match metadata["type"]:
            case "prompt":
                info = json.loads(reply.readAll().data().decode("utf-8"))
                comfy_error = ComfyError(info)

                if comfy_error.has_errors():
                    self.settings.log_json(info, label="ComfyUI Error", level=LogLevel.ERROR)
                    error = GraphError.from_comfyui_error(comfy_error)

                if error is not None:
                    prompt_id = metadata["prompt_id"]

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

            case "danbooru_tags":
                if error is None:
                    tags = json.loads(reply.readAll().data().decode("utf-8"))
                    self.process_danbooru_tags_chunk(tags)
                else:
                    self.last_danbooru_id = None
                    self.pending_danbooru_tags = None

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
        #self.update_danbooru_tags()


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


    # Removes all live mode prompts
    def clear_queue_live_mode(self):
        remove = [prompt for prompt in self.queue if prompt.is_live_mode]

        for prompt in remove:
            is_running = prompt.state.is_running()

            prompt.cancel()
            self.queue.remove(prompt)

            if is_running:
                self.interrupt_prompt(prompt)

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
            self.http.get(self.request(
                url=f"http://{self.url}/object_info",
                metadata={
                    "type": "object_info",
                },
            ))


    def all_danbooru_aliases(self, tag):
        for alias in tag.get("consequent_aliases", []):
            alias_name = alias["antecedent_name"]

            yield alias_name

            sub_tag = self.pending_danbooru_tags.get(alias_name, None)

            if sub_tag is not None:
                yield from self.all_danbooru_aliases(sub_tag)


    def save_danbooru_tags(self):
        try:
            danbooru_tags = {}

            for name, tag in self.pending_danbooru_tags.items():
                if not name in danbooru_tags:
                    danbooru_tags[name] = {
                        "post_count": tag["post_count"],
                        "category": tag["category"],
                    }

                    for alias in self.all_danbooru_aliases(tag):
                        danbooru_tags[alias] = {
                            "alias_for": name,
                        }

            self.settings.save_danbooru_tags(danbooru_tags)

        finally:
            self.last_danbooru_id = None
            self.pending_danbooru_tags = None


    def process_danbooru_tags_chunk(self, tags):
        if len(tags) == 0:
            self.save_danbooru_tags()

        else:
            for tag in tags:
                self.last_danbooru_id = tag["id"]

                name = tag["name"]
                assert not name in self.pending_danbooru_tags
                self.pending_danbooru_tags[name] = tag

            self.update_danbooru_tags()


    def update_danbooru_tags(self):
        if self.last_danbooru_id is None:
            assert self.pending_danbooru_tags is None
            self.pending_danbooru_tags = {}
            page = None
        else:
            page = f"b{self.last_danbooru_id}"

        self.http.get(self.request(
            url="https://danbooru.donmai.us/tags.json",
            query={
                "limit": "1000",
                "search[hide_empty]": "yes",
                "search[is_deprecated]": "no",
                "search[order]": "id",
                "only": "id,name,post_count,category,consequent_aliases[antecedent_name]",
                "page": page,
            },
            headers=[
                (QNetworkRequest.KnownHeaders.UserAgentHeader, "krita-plugin-comfyui/1.0"),
            ],
            metadata={
                "type": "danbooru_tags",
            },
        ))


    def execute_graph(self, graph, *, document_id, is_live_mode, should_notify=True):
        self.settings.log_json(graph.debug(), label="Execute Graph", level=LogLevel.DEBUG)

        graph_id = str(self.graph_id)

        self.graph_id += 1

        prompt = Prompt(document_id, self.client_id, graph_id, graph, is_live_mode, should_notify)

        self.queue.append(prompt)

        graph_info = prompt.graph_info()

        self.graph_changed.emit(graph_info)

        self.execute_queue()

        return graph_info
