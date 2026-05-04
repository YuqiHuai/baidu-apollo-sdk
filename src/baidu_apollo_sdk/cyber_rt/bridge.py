"""Low-level socket protocol client for Apollo cyber-bridge."""

import logging
import select
import socket
from collections import defaultdict
from collections.abc import Callable
from threading import Thread
from typing import Any, Protocol

from google.protobuf.descriptor import FileDescriptor

from .channel import Topic

logger = logging.getLogger(__name__)


class CyberBridgeContainer(Protocol):
    """Container interface needed by `CyberBridge`."""

    @property
    def ip_address(self) -> str:
        """Return the container IP address or host fallback."""
        ...

    @property
    def container_name(self) -> str:
        """Return the container runtime name."""
        ...


def to_bytes(s: str) -> bytes:
    """Convert a string to ASCII bytes.

    Args:
        s: String to encode.

    Returns:
        ASCII-encoded bytes.
    """
    return bytes(s, "ascii")


class BridgeOp:
    """Operation byte constants for the cyber-bridge wire protocol."""

    REGISTER_DESC = (1).to_bytes(1, byteorder="big")
    ADD_READER = (2).to_bytes(1, byteorder="big")
    """Register a subscriber"""
    ADD_WRITER = (3).to_bytes(1, byteorder="big")
    """Register a publisher"""
    PUBLISH = (4).to_bytes(1, byteorder="big")
    """Publish a message"""


class CyberBridge:
    """Low-level cyber-bridge socket connection.

    Args:
        container: Apollo container running cyber-bridge.
        port: TCP port for cyber-bridge.
    """

    container: CyberBridgeContainer
    conn: socket.socket
    subscribers: defaultdict[str, list[Callable[[bytes], None]]]
    publishable_channel: set[str]
    spinning: bool
    t: Thread | None

    def __init__(
        self, container: CyberBridgeContainer, port: int = 9090
    ) -> None:
        """Connect to the cyber-bridge endpoint in a container.

        Args:
            container: Apollo container running cyber-bridge.
            port: TCP port for cyber-bridge.
        """
        self.container = container
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((container.ip_address, port))
        self.conn.setblocking(False)
        self.subscribers = defaultdict(list)
        self.publishable_channel = set()
        self._registered_proto_descriptors: set[str] = set()
        self.spinning = False
        self._buffer = b""
        self.t = None

    @staticmethod
    def __prepare_bytes(data: bytes) -> bytes:
        """Prefix a byte payload with its 32-bit little-endian length.

        Args:
            data: Payload bytes.

        Returns:
            Length-prefixed payload bytes.
        """
        result = b""
        shifts = [0, 8, 16, 24]
        for s in shifts:
            result += (
                (len(data) >> s).to_bytes(4, byteorder="big")[-1]
            ).to_bytes(1, byteorder="big")
        result += data
        return result

    def __send(self, data: bytes) -> None:
        """Send all bytes over the non-blocking bridge socket.

        Args:
            data: Complete wire-protocol packet to send.

        Raises:
            TimeoutError: If the socket does not become writable.
        """
        offset = 0
        while offset < len(data):
            _, writable, _ = select.select([], [self.conn], [], 5.0)
            if not writable:
                raise TimeoutError("Timed out waiting for cyber bridge socket")
            offset += self.conn.send(data[offset:])

    def __collect_proto_descriptors(
        self,
        descriptor: FileDescriptor,
        result: list[FileDescriptor],
    ) -> None:
        """Collect unregistered protobuf descriptors in dependency order.

        Args:
            descriptor: File descriptor to register.
            result: Mutable list populated with descriptors to send.
        """
        if descriptor.name in self._registered_proto_descriptors:
            return

        for dependency in descriptor.dependencies:
            self.__collect_proto_descriptors(dependency, result)

        self._registered_proto_descriptors.add(descriptor.name)
        result.append(descriptor)

    def register_proto_descriptor(self, descriptor: FileDescriptor) -> None:
        """Register protobuf file descriptors with cyber-bridge.

        Args:
            descriptor: Protobuf file descriptor for a published message type.
        """
        descriptors: list[FileDescriptor] = []
        self.__collect_proto_descriptors(descriptor, descriptors)
        if not descriptors:
            return

        data = BridgeOp.REGISTER_DESC
        data += len(descriptors).to_bytes(4, byteorder="little")
        for proto_descriptor in descriptors:
            data += self.__prepare_bytes(proto_descriptor.serialized_pb)

        self.__send(data)

    def add_subscriber(
        self,
        topic: Topic[Any],
        cb: Callable[[bytes], None],
    ) -> None:
        """Register a subscriber callback with cyber-bridge.

        Args:
            topic: Topic descriptor to subscribe to.
            cb: Callback invoked with raw message bytes.
        """
        topic_msg_type = topic.msg_type

        data = BridgeOp.ADD_READER
        data += self.__prepare_bytes(to_bytes(topic.channel))
        data += self.__prepare_bytes(to_bytes(topic_msg_type))

        self.__send(data)
        self.subscribers[topic.channel].append(cb)

    def add_publisher(self, topic: Topic[Any]) -> None:
        """Register a publisher with cyber-bridge.

        Args:
            topic: Topic descriptor to publish to.
        """
        if topic.channel in self.publishable_channel:
            return

        if topic.proto_descriptor is not None:
            self.register_proto_descriptor(topic.proto_descriptor)

        topic_msg_type = topic.msg_type

        data = BridgeOp.ADD_WRITER
        data += self.__prepare_bytes(to_bytes(topic.channel))
        data += self.__prepare_bytes(to_bytes(topic_msg_type))
        self.__send(data)
        self.publishable_channel.add(topic.channel)

    def on_read(self, data: bytes) -> None:
        """Dispatch a complete inbound wire-protocol packet.

        Args:
            data: Complete packet received from cyber-bridge.
        """
        op = data[0]
        if op == int.from_bytes(BridgeOp.PUBLISH, "big"):
            self.receive_publish(data)
        else:
            pass

    def __get_32_le(self, b: bytes) -> int:
        """Convert 4 little-endian bytes to an integer.

        Args:
            b: Four bytes representing a 32-bit little-endian integer.

        Returns:
            Converted integer.
        """
        assert len(b) == 4, f"Expecting 4 bytes, got {len(b)}"
        b0 = b[0]
        b1 = b[1]
        b2 = b[2]
        b3 = b[3]
        return b0 | b1 << 8 | b2 << 16 | b3 << 24

    def receive_publish(self, data: bytes) -> None:
        """Parse a publish packet and invoke local subscribers.

        Args:
            data: Complete publish packet received from cyber-bridge.
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

    def publish(self, topic: Topic[Any], data: bytes) -> None:
        """Publish raw message bytes through cyber-bridge.

        Args:
            topic: Topic descriptor to publish to.
            data: Serialized protobuf payload.

        Raises:
            AssertionError: If `data` is not exactly `bytes`.
        """
        assert isinstance(data, bytes)
        msg = BridgeOp.PUBLISH
        msg += self.__prepare_bytes(to_bytes(topic.channel))
        msg += self.__prepare_bytes(data)
        self.__send(msg)

    def _process_buffer(self) -> None:
        """Process complete packets accumulated in the receive buffer."""
        while True:
            if len(self._buffer) < 1:
                return

            op = self._buffer[0]
            logger.debug("Received op: %s", op)

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
            logger.debug("Received topic: %s", topic.decode("ascii"))
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
        """Read socket data until the bridge is stopped or the socket fails."""
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
                logger.error("Socket error: %s", e)
                break

            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Unexpected error in _spin loop")
                break

        self.spinning = False

    def spin(self) -> None:
        """Start the socket receive loop in a background thread."""
        if self.spinning:
            return
        self.spinning = True
        self.t = Thread(target=self._spin)
        self.t.start()

    def stop(self) -> None:
        """Stop the socket receive loop and wait for its thread to exit."""
        self.spinning = False
        if self.t is not None:
            self.t.join()
