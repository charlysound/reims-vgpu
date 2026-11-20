#!/usr/bin/python3
"""Replay a press, hover and release with the live X11 cursor."""

import argparse
import math
import subprocess
import time

from Xlib import display


def point(value):
    x, y = value.split(",")
    return int(x), int(y)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--target", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--guest-source", action="store_true")
    parser.add_argument("--guest-target", action="store_true")
    parser.add_argument("--edge", type=point)
    parser.add_argument("--pause", type=float, default=.38)
    parser.add_argument("start", type=point)
    parser.add_argument("hover", type=point)
    parser.add_argument("end", type=point)
    args = parser.parse_args()
    connection = display.Display()
    root = connection.screen().root

    def location(window_id, is_guest, pos):
        window = connection.create_resource_object("window", window_id)
        x, y = pos
        if is_guest:
            bounds = window.get_geometry()
            scale = min(bounds.width / 1920, bounds.height / 1080)
            x = round((bounds.width - 1920 * scale) / 2 + scale * x)
            y = round((bounds.height - 1080 * scale) / 2 + scale * y)
        coord = root.translate_coords(window, x, y)
        return coord.x, coord.y

    def tool(*args):
        subprocess.run(["xdotool", *map(str, args)], check=True)

    def move(start, end):
        distance = math.dist(start, end)
        steps = max(1, math.ceil(distance / 37))
        for step in range(1, steps + 1):
            x, y = (round(a + (b - a) * step / steps) for a, b in zip(start, end))
            tool("mousemove", x, y)
            time.sleep(.016)

    source = location(args.source, args.guest_source, args.start)
    hover = location(args.target, args.guest_target, args.hover)
    end = location(args.target, args.guest_target, args.end)
    print(f"Pointer press {source}, hover {hover}, release {end}", flush=True)
    tool("mousemove", *source)
    time.sleep(.25)
    tool("mousedown", 1)
    try:
        if args.edge is not None:
            edge = location(args.source, args.guest_source, args.edge)
            move(source, edge)
            time.sleep(args.pause)
            source = edge
        move(source, hover)
        time.sleep(args.pause)
        move(hover, end)
        time.sleep(args.pause)
    finally:
        tool("mouseup", 1)


if __name__ == "__main__":
    main()
