from aiohttp import web
import threading
import asyncio
import json


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

            print("SERVER STARTED")

            # Wait for the shutdown event
            await event.wait()

        # When the shutdown event happens, gracefully cleanup the server
        finally:
            print("CLEANUP")
            await runner.cleanup()
            print("CLEANUP DONE")

    # Runs the run_async future in the event loop
    # This blocks the thread until it finishes
    def run(loop, routes, event, host, port):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_async(routes, event, host, port))

    # Calls the run function in another thread
    thread = threading.Thread(target=run, args=(loop, routes, event, host, port))
    thread.start()

    return thread


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
            print("KRITA-LAYERS")

            name = request.query["name"]
            mode = request.query["mode"]

            print(name)
            print(mode)

            return web.Response(text=json.dumps({
                "foo": "HI",
                "name": name,
                "mode": mode,
            }))

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
