"""Intercambio local Python–Whisk3D por memoria compartida de Windows."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import mmap
import os
import secrets
import struct

FRAME_SIZE = 16384
ACK_SIZE = 256
ACK_OFFSET = 4 + FRAME_SIZE
INPUT_OFFSET = ACK_OFFSET + 4 + ACK_SIZE
INPUT_CAPACITY = 128
TOTAL_SIZE = INPUT_OFFSET + 4 + 8 * INPUT_CAPACITY


class LocalChannel:
    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("El visor incluido usa el canal local de Windows.")
        self.name = "Local\\FTI_" + secrets.token_hex(16)
        self.sequence = 0
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        for name in ("WaitForSingleObject", "ReleaseMutex", "CloseHandle"):
            method = getattr(self.kernel, name)
            method.argtypes = (wintypes.HANDLE, wintypes.DWORD) if name == "WaitForSingleObject" else (wintypes.HANDLE,)
            method.restype = wintypes.DWORD if name == "WaitForSingleObject" else wintypes.BOOL
        self.mutex = self.kernel.CreateMutexW(None, False, self.name + "_mtx")
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.memory = mmap.mmap(-1, TOTAL_SIZE, tagname=self.name)
        except OSError:
            self.kernel.CloseHandle(self.mutex)
            raise

    @contextmanager
    def _lock(self):
        result = self.kernel.WaitForSingleObject(self.mutex, 0)
        if result not in (0, 0x80, 0x102):
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = result != 0x102
        try:
            yield acquired
        finally:
            if acquired:
                self.kernel.ReleaseMutex(self.mutex)

    def publish(self, state):
        serial = self.sequence + 1
        lights = " ".join(state["lights"][side] for side in "NESW")
        rows = [f"FTI2 {serial} {state['epoch']} {state['time']:.4f} {state['view']} "
                f"{state['azimuth']:.2f} {state['elevation']:.2f} {lights} {len(state['cars'])} "
                f"{state['command']} {int(state['paused'])} {state['zoom']} {state['scenario']} "
                f"{state['mode']} {int(state['sensors'])}"]
        for car in state["cars"]:
            rows.append(f"{car['id']} {car['model']} {car['slot']} {car['x']:.4f} "
                        f"{car['z']:.4f} {car['yaw']:.5f}")
        payload = ("\n".join(rows) + "\n").encode("ascii")
        if len(payload) > FRAME_SIZE:
            raise ValueError("La escena excedió la capacidad del canal local.")
        with self._lock() as acquired:
            if not acquired:
                return False
            self.memory[4:4 + len(payload)] = payload
            struct.pack_into("<I", self.memory, 0, len(payload))
            self.sequence = serial
        return True

    def read_ack(self):
        with self._lock() as acquired:
            if not acquired:
                return None
            size, = struct.unpack_from("<I", self.memory, ACK_OFFSET)
            if not 0 < size <= ACK_SIZE:
                return None
            raw = self.memory[ACK_OFFSET + 4:ACK_OFFSET + 4 + size]
        try:
            (version, sequence, epoch, count, view, azimuth, elevation, zoom,
             command, paused, sensors, scenario, mode, *lights) = raw.decode("ascii").split()
            sequence, epoch, count, zoom, command = map(int, (sequence, epoch, count, zoom, command))
            azimuth, elevation = float(azimuth), float(elevation)
        except (ValueError, UnicodeError):
            return None
        if (version != "FTI2" or not 0 < sequence <= self.sequence
                or epoch < 0 or command < 0 or not 0 <= count <= 72
                or not 0 <= azimuth <= 360 or not 12 <= elevation <= 87 or not 60 <= zoom <= 175
                or paused not in ("0", "1") or sensors not in ("0", "1")
                or len(lights) != 4 or any(color not in ("RED", "YELLOW", "GREEN") for color in lights)):
            return None
        return {"sequence": sequence, "epoch": epoch, "count": count,
                "view": view, "azimuth": azimuth, "elevation": elevation,
                "zoom": zoom, "command": command, "paused": paused == "1",
                "sensors": sensors == "1", "scenario": scenario, "mode": mode,
                "lights": dict(zip("NESW", lights))}

    def read_actions(self):
        with self._lock() as acquired:
            if not acquired:
                return ()
            count, = struct.unpack_from("<I", self.memory, INPUT_OFFSET)
            struct.pack_into("<I", self.memory, INPUT_OFFSET, 0)
            if not 0 < count <= INPUT_CAPACITY:
                return ()
            start = INPUT_OFFSET + 4
            return tuple(struct.iter_unpack("<ii", self.memory[start:start + 8 * count]))

    def close(self):
        if not self.memory.closed:
            self.memory.close()
            self.kernel.CloseHandle(self.mutex)
