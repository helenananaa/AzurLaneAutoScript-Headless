"""Fail-closed audit sentinel for framebuffer access in semantic mode."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from .errors import UnsupportedPixelRead
from .frame import SemanticFrame


_CONSUMER_PATTERN = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")


class PixelAccessOperation(str, Enum):
    ARRAY_CONVERSION = "array-conversion"
    ARRAY_FUNCTION = "array-function"
    ARRAY_METADATA = "array-metadata"
    ARRAY_TRUTH = "array-truth"
    BUFFER_EXPORT = "buffer-export"
    COPY = "copy"
    CROP = "crop"
    IMAGE_ATTRIBUTE = "image-attribute"
    ITERATION = "iteration"
    NUMPY_COERCION = "numpy-coercion"
    OPENCV_COERCION = "opencv-coercion"
    PIXEL_INDEX = "pixel-index"
    SLICE = "slice"
    TEMPLATE_ACCESS = "template-access"


@dataclass(frozen=True)
class PixelAccessRecord:
    ordinal: int
    frame_id: str
    generation: int
    operation: PixelAccessOperation
    consumer: str

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int):
            raise TypeError("pixel audit ordinal must be an integer")
        if self.ordinal <= 0:
            raise ValueError("pixel audit ordinal must be positive")
        if not isinstance(self.frame_id, str) or not self.frame_id:
            raise ValueError("pixel audit frame ID is required")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise TypeError("pixel audit generation must be an integer")
        if self.generation < 0:
            raise ValueError("pixel audit generation must be non-negative")
        if not isinstance(self.operation, PixelAccessOperation):
            raise TypeError("pixel audit operation must be classified")
        if (
            not isinstance(self.consumer, str)
            or _CONSUMER_PATTERN.fullmatch(self.consumer) is None
        ):
            raise ValueError("pixel audit consumer is malformed")


class PixelAccessAudit:
    """Record every rejected pixel access without ever admitting one."""

    def __init__(
        self,
        sink: Callable[[PixelAccessRecord], None] | None = None,
    ) -> None:
        if sink is not None and not callable(sink):
            raise TypeError("pixel audit sink must be callable")
        self._sink = sink
        self._records: list[PixelAccessRecord] = []
        self._lock = threading.Lock()

    def records(self) -> tuple[PixelAccessRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def reject(
        self,
        frame: SemanticFrame,
        operation: PixelAccessOperation,
        consumer: str,
    ) -> None:
        if not isinstance(frame, SemanticFrame):
            raise TypeError("pixel audit requires a semantic frame")
        if not isinstance(operation, PixelAccessOperation):
            raise TypeError("pixel access operation must be classified")
        if (
            not isinstance(consumer, str)
            or _CONSUMER_PATTERN.fullmatch(consumer) is None
        ):
            raise ValueError("pixel access consumer is malformed")
        with self._lock:
            record = PixelAccessRecord(
                ordinal=len(self._records) + 1,
                frame_id=frame.frame_id,
                generation=frame.generation,
                operation=operation,
                consumer=consumer,
            )
            self._records.append(record)
        if self._sink is not None:
            try:
                self._sink(record)
            except Exception:
                # The in-memory audit is already durable for this process.
                # Telemetry failure must not replace the classified rejection.
                pass
        raise UnsupportedPixelRead()


class SemanticPixelGuard:
    """A non-array image placeholder that classifies every attempted access."""

    __array_priority__ = 10_000
    __slots__ = ("__audit", "__frame")

    def __init__(self, frame: SemanticFrame, audit: PixelAccessAudit) -> None:
        if not isinstance(frame, SemanticFrame):
            raise TypeError("semantic pixel guard requires a frame")
        if not isinstance(audit, PixelAccessAudit):
            raise TypeError("semantic pixel guard requires an audit recorder")
        self.__frame = frame
        self.__audit = audit

    @property
    def frame_id(self) -> str:
        return self.__frame.frame_id

    @property
    def generation(self) -> int:
        return self.__frame.generation

    def reject(
        self,
        operation: PixelAccessOperation,
        consumer: str,
    ) -> None:
        self.__audit.reject(self.__frame, operation, consumer)

    def __array__(self, dtype: Any = None, copy: Any = None) -> Any:
        del dtype, copy
        self.reject(PixelAccessOperation.NUMPY_COERCION, "numpy.asarray")

    @property
    def __array_interface__(self) -> Any:
        self.reject(PixelAccessOperation.NUMPY_COERCION, "numpy.array-interface")

    @property
    def __array_struct__(self) -> Any:
        self.reject(PixelAccessOperation.NUMPY_COERCION, "numpy.array-struct")

    def __array_function__(self, func: Any, types: Any, args: Any, kwargs: Any) -> Any:
        del func, types, args, kwargs
        self.reject(PixelAccessOperation.ARRAY_FUNCTION, "numpy.array-function")

    def __array_ufunc__(
        self,
        ufunc: Any,
        method: Any,
        *inputs: Any,
        **kwargs: Any,
    ) -> Any:
        del ufunc, method, inputs, kwargs
        self.reject(PixelAccessOperation.ARRAY_FUNCTION, "numpy.array-ufunc")

    def __getitem__(self, key: Any) -> Any:
        operation = (
            PixelAccessOperation.SLICE
            if isinstance(key, slice)
            or (
                isinstance(key, tuple)
                and any(isinstance(item, slice) for item in key)
            )
            else PixelAccessOperation.PIXEL_INDEX
        )
        self.reject(operation, "python.getitem")

    def __iter__(self) -> Any:
        self.reject(PixelAccessOperation.ITERATION, "python.iter")

    def __len__(self) -> int:
        self.reject(PixelAccessOperation.ARRAY_METADATA, "python.len")

    def __bool__(self) -> bool:
        self.reject(PixelAccessOperation.ARRAY_TRUTH, "python.bool")

    def __bytes__(self) -> bytes:
        self.reject(PixelAccessOperation.BUFFER_EXPORT, "python.bytes")

    @property
    def shape(self) -> Any:
        self.reject(PixelAccessOperation.ARRAY_METADATA, "numpy.shape")

    @property
    def dtype(self) -> Any:
        self.reject(PixelAccessOperation.ARRAY_METADATA, "numpy.dtype")

    @property
    def ndim(self) -> Any:
        self.reject(PixelAccessOperation.ARRAY_METADATA, "numpy.ndim")

    @property
    def size(self) -> Any:
        self.reject(PixelAccessOperation.ARRAY_METADATA, "numpy.size")

    @property
    def data(self) -> Any:
        self.reject(PixelAccessOperation.BUFFER_EXPORT, "numpy.data")

    def copy(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.reject(PixelAccessOperation.COPY, "image.copy")

    def crop(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.reject(PixelAccessOperation.CROP, "image.crop")

    def convert(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.reject(PixelAccessOperation.ARRAY_CONVERSION, "image.convert")

    def opencv_input(self, consumer: str) -> None:
        self.reject(PixelAccessOperation.OPENCV_COERCION, consumer)

    def template_input(self, consumer: str) -> None:
        self.reject(PixelAccessOperation.TEMPLATE_ACCESS, consumer)

    def __getattr__(self, name: str) -> Any:
        consumer = "image.attribute-{0}".format(name)
        if _CONSUMER_PATTERN.fullmatch(consumer) is None:
            consumer = "image.attribute-unknown"
        self.reject(PixelAccessOperation.IMAGE_ATTRIBUTE, consumer)

    def __repr__(self) -> str:
        return "SemanticPixelGuard(frame_id={0!r}, generation={1})".format(
            self.frame_id,
            self.generation,
        )
