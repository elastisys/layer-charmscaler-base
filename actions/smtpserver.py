#!/usr/bin/env python3.5
import asyncio
import logging
import sys

sys.path.append("lib")
from charms.layer.basic import activate_venv  # noqa: E402
activate_venv()

from aiosmtpd.controller import Controller  # noqa: E402
from aiosmtpd.handlers import Message  # noqa: E402
from aiozmq import rpc  # noqa: E402
from charmhelpers.core import hookenv  # noqa: E402
import zmq  # noqa: E402


class Inbox(Message):
    def __init__(self):
        self.mail = list()
        super().__init__()

    @property
    def count(self):
        return len(self.mail)

    def handle_message(self, message):
        self.mail.append(message)


class SMTPHandler(rpc.AttrHandler):
    def __init__(self):
        self.inbox = Inbox()
        self.controller = Controller(self.inbox, port=0, ready_timeout=1)
        self.controller.start()

    @property
    def port(self):
        return self.controller.server.sockets[0].getsockname()[1]

    @property
    def running(self):
        return self.controller.thread.is_alive()

    @rpc.method
    def inboxcount(self):
        return self.inbox.count

    @rpc.method
    def stop(self):
        # TODO Call later is currently needed to let the RPC client recieve a
        #      response before the server exits.
        # See: https://github.com/aio-libs/aiozmq/issues/39
        loop = asyncio.get_event_loop()
        loop.call_later(0.01, self.controller.stop)


class Server:
    @classmethod
    async def start(cls):
        self = cls()
        self.smtp = SMTPHandler()
        self.server = await rpc.serve_rpc(self.smtp, bind="tcp://127.0.0.1:*")
        return self

    @property
    def port(self):
        return list(self.server.transport.bindings())[0].split(':')[-1]

    async def wait(self):
        while self.smtp.running:
            await asyncio.sleep(0)

    async def stop(self):
        if self.smtp is not None and self.smtp.running:
            self.smtp.stop()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


class Client:
    @classmethod
    async def connect(cls, port):
        self = cls()
        address = "tcp://127.0.0.1:{}".format(port)
        self.client = await rpc.connect_rpc(connect=address, timeout=3)
        self.client.transport.setsockopt(zmq.LINGER, 0)
        return self

    def __getattr__(self, name):
        return getattr(self.client.call, name)


async def server():
    server = await Server.start()

    ports = {
        "ports.rpc": server.port,
        "ports.smtp": server.smtp.port
    }
    hookenv.log("SMTP server started - ports: {}".format(ports))
    hookenv.action_set(ports)

    try:
        await server.wait()
    except KeyboardInterrupt:
        pass

    await server.stop()


async def client(op):
    try:
        port = hookenv.action_get("port")
        client = await Client.connect(port)

        if op == "inboxcount":
            count = await client.inboxcount()
            hookenv.action_set({"count": count})
            hookenv.log("SMTP server inbox count: {}".format(count))
        elif op == "stop":
            await client.stop()
            hookenv.log("SMTP server successfully stopped")
    except asyncio.TimeoutError:
        raise Exception("SMTP server RPC connection timed out")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("asyncio").setLevel(logging.INFO)

    op = hookenv.action_get("operation")

    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(server() if op == "start" else client(op))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        msg = str(e)
        hookenv.action_fail(msg)
        hookenv.log(msg, level=hookenv.ERROR)
    finally:
        for task in asyncio.Task.all_tasks():
            task.cancel()
        loop.stop()
        loop.close()
