import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import serial
from pydantic import BaseModel, Field, validator
from serial.tools import list_ports

logger = logging.getLogger(__name__)


@dataclass
class SerialCommand:
    payload: str


class SerialConfiguration(BaseModel):
    port: Optional[str] = Field(default=None)
    baud_rate: int = Field(default=9600)
    parity: str = Field(default="N")
    stop_bits: float = Field(default=1.0)

    @validator("parity")
    def validate_parity(cls, value: str) -> str:
        allowed = {"N", "E", "O", "M", "S"}
        upper_value = value.upper()
        if upper_value not in allowed:
            raise ValueError(f"Unsupported parity: {value}")
        return upper_value

    @validator("stop_bits")
    def validate_stop_bits(cls, value: float) -> float:
        allowed = {1, 1.5, 2}
        if value not in allowed:
            raise ValueError(f"Unsupported stop bits: {value}")
        return float(value)


class SerialService:
    """Asynchronous serial command dispatcher."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[SerialCommand] = asyncio.Queue()
        self._serial: Optional[serial.SerialBase] = None
        self._config = SerialConfiguration()
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = asyncio.Event()
        self._reconfigure_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker(), name="serial-service-worker")

    async def stop(self) -> None:
        self._shutdown.set()
        if self._task:
            await self._queue.put(SerialCommand(payload=""))  # unblock queue
            await self._task
            self._task = None
        await self._close_serial()

    async def send_command(self, payload: str) -> None:
        command = SerialCommand(payload=payload)
        await self._queue.put(command)

    async def apply_configuration(self, config: SerialConfiguration) -> None:
        async with self._lock:
            self._config = config
            self._reconfigure_event.set()
            await self._close_serial_locked()
        await self._queue.put(SerialCommand(payload=""))

    async def _worker(self) -> None:
        while not self._shutdown.is_set():
            command = await self._queue.get()
            if self._shutdown.is_set():
                break

            if not command.payload and self._reconfigure_event.is_set():
                self._reconfigure_event.clear()
                continue

            try:
                await self._ensure_connection()
                await self._write(command.payload)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Serial write failed: %s", exc)

    async def _ensure_connection(self) -> None:
        if self._serial and self._serial.is_open:
            return

        async with self._lock:
            if self._serial and self._serial.is_open:
                return

            if not self._config.port:
                raise RuntimeError("Serial port is not configured.")

            self._serial = await asyncio.to_thread(self._open_serial_sync, self._config)

    async def _write(self, payload: str) -> None:
        if not self._serial:
            raise RuntimeError("Serial port is not connected.")

        data = payload.encode("utf-8")
        await asyncio.to_thread(self._serial.write, data)
        await asyncio.to_thread(self._serial.flush)

    async def _close_serial(self) -> None:
        async with self._lock:
            await self._close_serial_locked()

    async def _close_serial_locked(self) -> None:
        if self._serial and self._serial.is_open:
            await asyncio.to_thread(self._serial.close)
        self._serial = None

    @staticmethod
    def _open_serial_sync(config: SerialConfiguration) -> serial.SerialBase:
        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        stop_bits_map = {
            1.0: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2.0: serial.STOPBITS_TWO,
        }

        if not config.port:
            raise RuntimeError("Serial port is not defined.")

        logger.info(
            "Opening serial port %s (baud=%s parity=%s stop=%s)",
            config.port,
            config.baud_rate,
            config.parity,
            config.stop_bits,
        )

        return serial.Serial(
            port=config.port,
            baudrate=config.baud_rate,
            parity=parity_map[config.parity],
            stopbits=stop_bits_map[config.stop_bits],
            timeout=1,
            write_timeout=1,
        )

    @staticmethod
    def available_ports() -> List[Dict[str, str]]:
        ports = []
        for port in sorted(list_ports.comports(), key=lambda p: p.device):
            ports.append(
                {
                    "device": port.device,
                    "description": port.description or port.device,
                }
            )
        return ports
