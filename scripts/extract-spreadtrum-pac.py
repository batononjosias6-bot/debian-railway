#!/usr/bin/env python3
"""Extract a Spreadtrum/Unisoc PAC file without modifying the input file."""

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path


WIDE_VERSION_BYTES = 24 * 2
WIDE_PRODUCT_BYTES = 256 * 2
WIDE_FIRMWARE_BYTES = 256 * 2
PARTITION_NAME_BYTES = 256 * 2
FILE_NAME_BYTES = 512 * 2
PARTITION_SIZE_OFFSET = 4 + PARTITION_NAME_BYTES + FILE_NAME_BYTES
PARTITION_DATA_OFFSET = PARTITION_SIZE_OFFSET + 4 + 8
MIN_PARTITION_HEADER = PARTITION_DATA_OFFSET + 4
COPY_CHUNK_BYTES = 64 * 1024 * 1024


def read_exact(source, offset, length):
    source.seek(offset)
    data = source.read(length)
    if len(data) != length:
        raise ValueError(f"short read at 0x{offset:x}: expected {length} bytes")
    return data


def u32(buffer, offset=0):
    return struct.unpack_from("<I", buffer, offset)[0]


def utf16z(buffer):
    return buffer.decode("utf-16le", errors="strict").split("\0", 1)[0].strip()


def safe_name(name, index):
    candidate = Path(name).name
    if not candidate or candidate in {".", ".."}:
        candidate = f"partition-{index:02d}.bin"
    return candidate


def copy_partition(source, offset, size, destination):
    remaining = size
    digest = hashlib.sha256()
    with destination.open("xb") as target:
        source.seek(offset)
        while remaining:
            block = source.read(min(COPY_CHUNK_BYTES, remaining))
            if not block:
                raise ValueError(f"unexpected EOF while copying {destination.name}")
            target.write(block)
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pac", type=Path, help="input PAC file")
    parser.add_argument("output", type=Path, help="new, empty output directory")
    args = parser.parse_args()

    pac = args.pac.resolve()
    output = args.output.resolve()
    if not pac.is_file():
        parser.error(f"PAC file not found: {pac}")
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    pac_size = pac.stat().st_size
    with pac.open("rb") as source:
        header = read_exact(source, 0, WIDE_VERSION_BYTES + WIDE_PRODUCT_BYTES + WIDE_FIRMWARE_BYTES + 12)
        version = utf16z(header[:WIDE_VERSION_BYTES])
        product_start = WIDE_VERSION_BYTES
        firmware_start = product_start + WIDE_PRODUCT_BYTES
        metadata_start = firmware_start + WIDE_FIRMWARE_BYTES
        product = utf16z(header[product_start:firmware_start])
        firmware = utf16z(header[firmware_start:metadata_start])
        partition_count = u32(header, metadata_start + 4)
        table_offset = u32(header, metadata_start + 8)

        if not 1 <= partition_count <= 512:
            raise ValueError(f"invalid partition count: {partition_count}")
        if not 0 < table_offset < pac_size:
            raise ValueError(f"invalid partition table offset: 0x{table_offset:x}")

        print(f"PAC version: {version}")
        print(f"Product: {product}")
        print(f"Firmware: {firmware}")
        print(f"Partitions: {partition_count}")

        manifest = {
            "pac": str(pac),
            "pac_size": pac_size,
            "version": version,
            "product": product,
            "firmware": firmware,
            "partition_count": partition_count,
            "partition_table_offset": table_offset,
            "partitions": [],
        }
        current = table_offset
        used_names = set()

        for index in range(partition_count):
            header_size = u32(read_exact(source, current, 4))
            if header_size < MIN_PARTITION_HEADER or current + header_size > pac_size:
                raise ValueError(f"invalid header size for partition {index}: 0x{header_size:x}")
            part_header = read_exact(source, current, header_size)
            partition_name = utf16z(part_header[4:4 + PARTITION_NAME_BYTES])
            source_name_start = 4 + PARTITION_NAME_BYTES
            source_name = utf16z(part_header[source_name_start:source_name_start + FILE_NAME_BYTES])
            image_size = u32(part_header, PARTITION_SIZE_OFFSET)
            image_offset = u32(part_header, PARTITION_DATA_OFFSET)
            end_offset = image_offset + image_size

            record = {
                "index": index,
                "partition": partition_name,
                "source_name": source_name,
                "size": image_size,
                "offset": image_offset,
            }
            if image_size == 0:
                record["status"] = "empty"
                manifest["partitions"].append(record)
                current += header_size
                continue
            if image_offset == 0 or end_offset > pac_size:
                raise ValueError(f"invalid image extent for {source_name or partition_name}: 0x{image_offset:x}+0x{image_size:x}")

            name = safe_name(source_name, index)
            if name in used_names:
                name = f"{index:02d}-{name}"
            used_names.add(name)
            destination = output / name
            checksum = copy_partition(source, image_offset, image_size, destination)
            record.update({"output": name, "sha256": checksum, "status": "extracted"})
            manifest["partitions"].append(record)
            print(f"[{index + 1}/{partition_count}] {partition_name} -> {name} ({image_size} bytes)")
            current += header_size

    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Manifest written: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError, struct.error) as error:
        print(f"PAC extraction aborted: {error}", file=sys.stderr)
        sys.exit(1)
