import logging
import select
import socket
from collections import defaultdict
from collections.abc import Callable
from threading import Thread
from typing import Any

from .channel import Channel

logger = logging.getLogger(__name__)


def to_bytes(s: str) -> bytes:
    """
    Converts string to bytes using ascii

    :param str s: string to be converted
    :returns: bytes in ascii
    :rtype: bytes
    """
    return bytes(s, "ascii")


class BridgeOp:
    """
    Class representing cyber bridge operations.
    """

    RegisterDesc = (1).to_bytes(1, byteorder="big")
    AddReader = (2).to_bytes(1, byteorder="big")
    """Register a subscriber"""
    AddWriter = (3).to_bytes(1, byteorder="big")
    """Register a publisher"""
    Publish = (4).to_bytes(1, byteorder="big")
    """Publish a message"""


class CyberBridge:
    """
    Class to represent CyberBridge

    :param str host: IP address of cyber bridge running inside docker
    :param int port: port of the cyber bridge
    """

    conn: socket.socket
    subscribers: defaultdict[str, list[Callable[[bytes], None]]]
    publishable_channel: set[str]
    spinning: bool
    t: Thread | None

    def __init__(self, host: str, port: int = 9090) -> None:
        """
        Constructor
        """
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((host, port))
        self.conn.setblocking(False)
        self.subscribers = defaultdict(lambda: list())
        self.publishable_channel = set()
        self.spinning = False
        self._buffer = b""
        self.t = None

    @staticmethod
    def __prepare_bytes(data: bytes) -> bytes:
        """
        Transforms data into [length][data]

        :param bytes data: data to be sent

        :returns: prepared bytes ready to be sent to bridge
        :rtype: bytes
        """
        result = b""
        shifts = [0, 8, 16, 24]
        for s in shifts:
            result += ((len(data) >> s).to_bytes(4, byteorder="big")[-1]).to_bytes(
                1, byteorder="big"
            )
        result += data
        return result

    def add_subscriber(
        self,
        channel: Channel[Any],
        cb: Callable[[bytes], None],
    ) -> None:
        """
        Adds a subscriber to the bridge

        :param Channel channel: the channel to subscribe from
        :param Function cb: callback function that takes parsed data from bridge
        """
        topic_msg_type = channel.msg_type

        data = BridgeOp.AddReader
        data += self.__prepare_bytes(to_bytes(channel.channel))
        data += self.__prepare_bytes(to_bytes(topic_msg_type))

        self.conn.send(data)
        self.subscribers[channel.channel].append(cb)

    def add_publisher(self, channel: Channel[Any]) -> None:
        """
        Adds a publisher to the bridge

        :param Channel channel: the channel to publish message to
        """
        if channel.channel in self.publishable_channel:
            return

        topic_msg_type = channel.msg_type

        data = BridgeOp.AddWriter
        data += self.__prepare_bytes(to_bytes(channel.channel))
        data += self.__prepare_bytes(to_bytes(topic_msg_type))
        self.conn.send(data)
        self.publishable_channel.add(channel.channel)

    def on_read(self, data: bytes) -> None:
        """
        Function callback to notify bridge has published data

        :param bytes data: data received from bridge
        """
        op = data[0]
        if op == int.from_bytes(BridgeOp.Publish, "big"):
            self.receive_publish(data)
        else:
            pass

    def __get_32_le(self, b: bytes) -> int:
        """
        Converts 32 bit le integer to int

        :param bytes b: bytes representing a 32 bit integer

        :return: converted integer
        :rtype: int
        """
        assert len(b) == 4, f"Expecting 4 bytes, got {len(b)}"
        b0 = b[0]
        b1 = b[1]
        b2 = b[2]
        b3 = b[3]
        return b0 | b1 << 8 | b2 << 16 | b3 << 24

    def receive_publish(self, data: bytes) -> None:
        """
        Receives data published by bridge and calls subscribers

        :param bytes data: data received from bridge
        """
        if not self.spinning:
            return
        offset = 1
        topic_length = self.__get_32_le(data[offset : offset + 4])
        offset += 4
        topic = data[offset : offset + topic_length].decode("ascii")
        offset += topic_length
        message_size = self.__get_32_le(data[offset : offset + 4])
        offset += 4
        msg = data[offset : offset + message_size]

        for subscriber in self.subscribers[topic]:
            subscriber(msg)

    def publish(self, channel: Channel[Any], data: bytes) -> None:
        """
        Publish data to the bridge

        :param Channel channel: channel to publish data to
        :param bytes data: data to be published

        :note: You should register a publisher first before publishing any data
        """
        assert type(data) is bytes
        msg = BridgeOp.Publish
        msg += self.__prepare_bytes(to_bytes(channel.channel))
        msg += self.__prepare_bytes(data)
        self.conn.send(msg)

    def _process_buffer(self) -> None:
        while True:
            if len(self._buffer) < 1:
                return

            op = self._buffer[0]
            logger.debug(f"Received op: {op}")

            # Need at least 1 + 4 bytes for topic length
            if len(self._buffer) < 5:
                return

            offset = 1

            topic_length = self.__get_32_le(self._buffer[offset : offset + 4])
            offset += 4

            # Wait until full topic is available
            if len(self._buffer) < offset + topic_length + 4:
                return

            topic = self._buffer[offset : offset + topic_length]
            logger.debug(f"Received topic: {topic.decode('ascii')}")
            offset += topic_length

            message_size = self.__get_32_le(self._buffer[offset : offset + 4])
            offset += 4

            # Wait until full message arrives
            if len(self._buffer) < offset + message_size:
                return

            offset += message_size

            full_packet = self._buffer[:offset]
            self._buffer = self._buffer[offset:]

            self.on_read(full_packet)

    def _spin(self) -> None:
        while self.spinning:
            try:
                ready, _, _ = select.select([self.conn], [], [], 0.1)
                if not ready:
                    continue

                data = self.conn.recv(65527)
                self._buffer += data
                self._process_buffer()

            except ConnectionResetError:
                logger.error("Connection reset by peer")
                break

            except OSError as e:
                logger.error(f"Socket error: {e}")
                break

            except Exception:
                logger.exception("Unexpected error in _spin loop")
                break

        self.spinning = False

    def spin(self) -> None:
        """
        Starts to spin the cyber bridge client
        """
        if self.spinning:
            return
        self.spinning = True
        self.t = Thread(target=self._spin)
        self.t.start()

    def stop(self) -> None:
        """
        Stops the cyber bridge client
        """
        self.spinning = False
        if self.t is not None:
            self.t.join()
