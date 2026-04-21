from krita import Krita
from aiohttp import web
import threading
import asyncio
import json
from .layer import (Bounds, Layer, Image)


# Starts the web server in a separate thread
def start_server(loop, routes, event, host, port):
    async def run_async(routes, event, host, port):
        server = web.Application()
        server.add_routes(routes)

        runner = web.AppRunner(server)

        try:
            await runner.setup()

            site = web.TCPSite(runner, host, port)
            await site.start()

            # Wait for the shutdown event
            await event.wait()

        # When the shutdown event happens, gracefully cleanup the server
        finally:
            await runner.cleanup()

    # Runs the run_async future in the event loop
    # This blocks the thread until it finishes
    def run(loop, routes, event, host, port):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_async(routes, event, host, port))

    # Calls the run function in another thread
    thread = threading.Thread(target=run, args=(loop, routes, event, host, port))
    thread.start()

    return thread


def success(message):
    return web.Response(text=json.dumps(message))


def error(message):
    return web.Response(text=json.dumps({
        "error": message,
    }))


class Server:
    def __init__(self):
        # We need a custom event loop to run the async code
        self.event_loop = asyncio.new_event_loop()

        # The thread that the server will be running in
        self.thread = None

        # We set this event to gracefully cleanup the server
        self.shutdown_event = asyncio.Event()


    def setup_routes(self):
        routes = web.RouteTableDef()


        @routes.get("/krita-layers")
        async def krita_layers(request):
            name = request.query["name"]
            mode = request.query["mode"]
            format = request.query["format"]

            if format != "png":
                return error("format must be png")


            document = Krita.instance().activeDocument()

            if document is None:
                return error("Krita does not have an opened image")


            bounds = Bounds.from_qrect(document.bounds())

            layer = Layer(document.rootNode()).find_layer(name)

            if layer is None:
                return error("Could not find layer {}".format(name))


            images = []

            def add_image(layer):
                images.append({
                    "name": layer.name,
                    "png": layer.image(bounds).to_base64("png", 9),
                })


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
                return error("mode must be individual or flatten")


            return success({
                "images": images,
            })


        @routes.get("/krita-canvas")
        async def krita_canvas(request):
            format = request.query["format"]

            if format != "png":
                return error("format must be png")


            document = Krita.instance().activeDocument()

            if document is None:
                return error("Krita does not have an opened image")


            bounds = Bounds.from_qrect(document.bounds())

            image = Image(document.projection(bounds.x, bounds.y, bounds.width, bounds.height))

            return success({
                "png": image.to_base64("png", 9),
                "width": bounds.width,
                "height": bounds.height,
            })


        @routes.get("/krita-selection")
        async def krita_selection(request):
            document = Krita.instance().activeDocument()

            if document is None:
                return error("Krita does not have an opened image")

            bounds = Bounds.from_qrect(document.bounds())

            selection = document.selection()

            if selection is not None:
                selection = Bounds(selection.x(), selection.y(), selection.width(), selection.height()).clamp_to_parent(bounds)
            else:
                selection = bounds

            return success({
                "active": selection != bounds,
                "x": selection.x,
                "y": selection.y,
                "width": selection.width,
                "height": selection.height,
            })


        return routes


    def start(self):
        if self.thread is not None:
            raise RuntimeError("Cannot start server multiple times")

        # Starts the server in another thread
        self.thread = start_server(
            loop=self.event_loop,
            routes=self.setup_routes(),
            event=self.shutdown_event,
            host="localhost",
            port=8321,
        )


    def stop(self):
        # Events aren't thread safe, so we must use call_soon_threadsafe to
        # set the event inside of the event loop.
        self.event_loop.call_soon_threadsafe(self.shutdown_event.set)

        # Wait for the other thread to finish cleaning up the server
        if self.thread is not None:
            self.thread.join()
