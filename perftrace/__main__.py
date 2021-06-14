#!/usr/bin/env python3
import subprocess
import webbrowser
import tempfile
import argparse
import sys
import json
from typing import List, Generator, TypeVar, Tuple, TextIO, TypedDict
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto

T = TypeVar("T")


@dataclass
class Event:
    pid: int
    tid: int
    time: float  # in seconds
    comm: str
    stack: List[str] = field(default_factory=list)


class EventType(Enum):
    BEGIN = auto()
    END = auto()


@dataclass
class MergedEvent:
    event: Event
    event_type: EventType
    stack_top: int


def parse_events(infile: TextIO) -> Generator[Event, None, None]:
    new_event = True
    for line in infile:
        if new_event:
            comm, pid_tid, time = line.split()
            pid, tid = pid_tid.split("/")
            event = Event(
                comm=comm,
                pid=int(pid),
                tid=int(tid),
                time=float(time.strip(":")),
            )
            new_event = False
        else:
            if line.strip() == "":
                if len(event.stack) == 0:
                    event.stack.append("[[nostack]]")
                yield event
                new_event = True
            else:
                _addr, *sym = line.split()
                event.stack.insert(0, "".join(sym))


def mismatch(lhs: List[T], rhs: List[T]) -> int:
    for idx, (left, right) in enumerate(zip(lhs, rhs)):
        if left != right:
            return idx
    return min(len(lhs), len(rhs))


def merge_events(infile: TextIO) -> Generator[MergedEvent, None, None]:
    last_event_by_xid: TypedDict[Tuple[int, int], Event] = {}
    latest_time: float = 0.0
    event_id = 0
    depth_by_xid: TypedDict[Tuple[int, int], int] = defaultdict(lambda: 0)
    for event in parse_events(infile):
        event_id += 1
        xid: Tuple[int, int] = (event.pid, event.tid)
        latest_time = max(latest_time, event.time)
        if xid not in last_event_by_xid:
            for i, _frame in enumerate(event.stack):
                depth_by_xid[xid] += 1
                yield MergedEvent(event=event, event_type=EventType.BEGIN, stack_top=i)
        else:
            # find the common prefix in the stacks
            last_event = last_event_by_xid[xid]
            mismatch_idx = mismatch(last_event.stack, event.stack)

            if last_event.stack == event.stack:
                continue
            else:
                # yield end events for events stack elements that ended from top to bottom
                le_len = len(last_event.stack)
                last_event.time = event.time
                for i, _frame in enumerate(reversed(last_event.stack[mismatch_idx:])):
                    depth_by_xid[xid] -= 1
                    yield MergedEvent(
                        event=last_event,
                        event_type=EventType.END,
                        stack_top=(le_len - (i + 1)),
                    )

                # yield start events for events that began from bottom to top
                for i, _frame in enumerate(event.stack[mismatch_idx:]):
                    depth_by_xid[xid] += 1
                    yield MergedEvent(
                        event=event,
                        event_type=EventType.BEGIN,
                        stack_top=i + mismatch_idx,
                    )
        last_event_by_xid[xid] = event
        assert depth_by_xid[xid] == len(last_event_by_xid[xid].stack)

    for xid, last_event in last_event_by_xid.items():
        le_len = len(last_event.stack)
        for i, _frame in enumerate(last_event.stack[::-1]):
            depth_by_xid[xid] -= 1
            yield MergedEvent(
                event=last_event, event_type=EventType.END, stack_top=(le_len - (i + 1))
            )


def convert(infile: TextIO, outfile: TextIO):
    print("[", file=outfile)
    SEC_TO_MS = 1000000
    first_event = True
    for event in merge_events(infile):
        try:
            if not first_event:
                print(",", file=outfile)
            else:
                first_event = False
            json.dump(
                {
                    "name": event.event.stack[event.stack_top],
                    "cat": event.event.comm,
                    "ph": "B" if event.event_type == EventType.BEGIN else "E",
                    "ts": event.event.time * SEC_TO_MS,
                    "pid": event.event.pid,
                    "tid": event.event.tid,
                },
                outfile,
            )
        except IndexError:
            print(event)
            break
        except BrokenPipeError:
            sys.exit()
    print("]", file=outfile)


def record(args):
    cmd = ["perf", "record", "--call-graph", "dwarf", *args.args]
    subprocess.run(cmd)


def report(args):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        proc = subprocess.Popen(
            ["perf", "script", "-F", "time,ip,sym,comm,pid,tid", "--reltime", "--ns"],
            stdout=subprocess.PIPE, text=True
        )
        convert(proc.stdout, tmp)
    print(tmp.name)
    browser = webbrowser.get()
    browser.open("https://ui.perfetto.dev/v13.0.194/assets/catapult_trace_viewer.html")


def parse_args():
    parser = argparse.ArgumentParser(
        "perftrace",
        description="a trace collector and parser tool for use with chrome://tracing",
    )
    sp = parser.add_subparsers()
    convert_parser = sp.add_parser("convert")
    convert_parser.add_argument(
        "--infile", type=argparse.FileType("r"), default=sys.stdin, nargs="?"
    )
    convert_parser.add_argument(
        "--outfile", "-o", type=argparse.FileType("w"), default=sys.stdout, nargs="?"
    )
    convert_parser.set_defaults(func=lambda args: convert(args.infile, args.outfile))

    record_parser = sp.add_parser("record")
    record_parser.set_defaults(func=record)

    report_parser = sp.add_parser("report")
    report_parser.set_defaults(func=report)

    parser.set_defaults(func=lambda _args: parser.print_help())
    (known, unknown) = parser.parse_known_args()
    known.args = unknown
    return known


def main():
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
