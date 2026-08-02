"""Compatibility patch for pye3dc's local RSCP frame reassembly.

``E3DC_RSCP_local._receive()`` in python-e3dc performs a single
``socket.recv(BUFFER_SIZE)`` call and assumes the entire encrypted RSCP
frame arrived in that one read. TCP gives no such guarantee: larger
responses (e.g. ``EH_REQ_GET_SAVED_ERRORS`` on units with an extensive
saved-error history) can be split across multiple reads, which makes
``rscpFrameDecode`` fail with::

    struct.error: unpack requires a buffer of N bytes

This patch replaces ``_receive`` with a version that loops over
``socket.recv()`` calls, feeding each chunk through the existing
(stateful) ``RSCPEncryptDecrypt.decrypt()`` incrementally, until enough
decrypted bytes are available to satisfy the frame length declared in
the header. This mirrors the intended usage of ``decrypt()`` -- it
already tracks IV chaining and left-over partial blocks across calls,
it was just never invoked more than once by ``_receive``.

A fix has been proposed upstream:
https://github.com/fsantini/python-e3dc (see PR referenced in the
hacs-e3dc changelog). This module can be dropped once python-e3dc
ships the fix and the minimum version is bumped in ``manifest.json``.
"""

from __future__ import annotations

import copy
import logging
import struct

from e3dc import _e3dc_rscp_local
from e3dc._rscpLib import endianSwapUint16, rscpDecode

_LOGGER = logging.getLogger(__name__)

_PATCHED = False

# Mirrors the header format used by rscpFrameDecode() in _rscpLib.py.
_HEADER_FMT = "<HHIIIH"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)
_CRC_SIZE = struct.calcsize("<I")


def _receive_full_frame(self: _e3dc_rscp_local.E3DC_RSCP_local):
    """Read and decrypt a complete RSCP frame, looping over ``recv()``.

    Replacement for ``E3DC_RSCP_local._receive`` that keeps reading
    until the full encrypted frame has arrived, instead of assuming a
    single ``socket.recv()`` call returns it all.

    ``RSCPEncryptDecrypt.decrypt()`` is stateful across calls, but its
    default (``previouslyProcessedData=None``) bookkeeping only tracks
    how much of the *immediately preceding* chunk was consumed. That
    is not accurate once more than one chunk arrived with a partial
    (non-block-aligned) leftover, which silently corrupts the result
    for three or more reads. To stay correct regardless of how many
    reads are needed, we re-decrypt the whole accumulated ciphertext
    from scratch on a throwaway copy of the encrypt/decrypt state on
    every iteration, and only commit the real, persistent
    ``self.encdec`` state once we know the full frame is available --
    matching exactly what would happen if it had arrived in one read.
    """
    ciphertext = b""

    while True:
        chunk = self.socket.recv(_e3dc_rscp_local.BUFFER_SIZE)
        if len(chunk) == 0:
            raise _e3dc_rscp_local.RSCPKeyError
        ciphertext += chunk

        probe_encdec = copy.copy(self.encdec)
        plaintext = probe_encdec.decrypt(ciphertext)

        if len(plaintext) < _HEADER_SIZE:
            continue

        _, ctrl, _, _, _, length = struct.unpack(_HEADER_FMT, plaintext[:_HEADER_SIZE])
        ctrl = endianSwapUint16(ctrl)
        crc_len = _CRC_SIZE if ctrl & 0x10 else 0
        needed = _HEADER_SIZE + length + crc_len

        if len(plaintext) >= needed:
            if len(ciphertext) > len(chunk):
                _LOGGER.debug(
                    "RSCP frame reassembly: reassembled %d bytes across "
                    "multiple reads.",
                    len(ciphertext),
                )
            # Advance the real, persistent decrypt state exactly once,
            # as if the full ciphertext had arrived in a single read.
            final_plaintext = self.encdec.decrypt(ciphertext)
            return rscpDecode(final_plaintext)[0]

        _LOGGER.debug(
            "RSCP frame reassembly: got %d/%d bytes, reading more",
            len(plaintext),
            needed,
        )


def patch_rscp_frame_reassembly() -> None:
    """Patch pye3dc's local RSCP transport to reassemble split frames.

    Idempotent: safe to call multiple times / from multiple config
    entries.
    """
    global _PATCHED
    if _PATCHED:
        return

    _e3dc_rscp_local.E3DC_RSCP_local._receive = _receive_full_frame
    _PATCHED = True
    _LOGGER.debug(
        "Patched E3DC_RSCP_local._receive for multi-read RSCP frame "
        "reassembly (large EH/DIAG responses)."
    )
