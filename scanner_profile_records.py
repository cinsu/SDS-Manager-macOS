# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Lossless native profile record edits for documented on/off service-type flags.

Only replace fields in an existing ServiceType row. Other profile bytes remain intact.
"""

def read_service_types(data: bytes):
    found = []
    for line in data.splitlines():
        fields = line.split(b"\t")
        if fields[0] == b"ServiceType":
            if len(fields) != 38 or any(v not in (b"On", b"Off") for v in fields[1:]):
                raise ValueError("Unsupported ServiceType record (expected 37 On/Off fields)")
            found.append(tuple(v == b"On" for v in fields[1:]))
    if len(found) != 1:
        raise ValueError("Expected exactly one ServiceType record")
    return found[0]


def patch_service_types(data: bytes, states):
    if len(states) != 37 or any(type(v) is not bool for v in states):
        raise ValueError("Expected 37 boolean ServiceType states")
    read_service_types(data)
    result = []
    for line in data.splitlines(keepends=True):
        if line.split(b"\t", 1)[0] == b"ServiceType":
            ending = b"\r\n" if line.endswith(b"\r\n") else (b"\n" if line.endswith(b"\n") else b"")
            line = b"ServiceType\t" + b"\t".join(b"On" if x else b"Off" for x in states) + ending
        result.append(line)
    return b"".join(result)


def read_custom_service_types(data: bytes):
    found = []
    for line in data.splitlines():
        fields = line.split(b"\t")
        if fields[0] == b"CustomServiceType":
            if len(fields) != 11 or any(v not in (b"On", b"Off") for v in fields[1:]):
                raise ValueError("Unsupported CustomServiceType record (expected 10 On/Off fields)")
            found.append(tuple(v == b"On" for v in fields[1:]))
    if len(found) != 1:
        raise ValueError("Expected exactly one CustomServiceType record")
    return found[0]

def patch_custom_service_types(data: bytes, states):
    if len(states) != 10 or any(type(v) is not bool for v in states):
        raise ValueError("Expected 10 boolean CustomServiceType states")
    read_custom_service_types(data)
    result = []
    for line in data.splitlines(keepends=True):
        if line.split(b"\t", 1)[0] == b"CustomServiceType":
            ending = b"\r\n" if line.endswith(b"\r\n") else (b"\n" if line.endswith(b"\n") else b"")
            line = b"CustomServiceType\t" + b"\t".join(b"On" if x else b"Off" for x in states) + ending
        result.append(line)
    return b"".join(result)
