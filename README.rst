===================
preftrace
===================

preftrace is a utility script that provides a ease of use layer over linux
`pref` for collecting trace information.  For best results compile applications
and libraries with the equivalent of `-fno-omit-frame-pointer` for your
compiler.

====================
Usage
====================

  #basic usage
  preftrace -h
  usage: perftrace [-h] {convert,record,report} ...

  a trace collector and parser tool for use with chrome://tracing

  positional arguments:
    {convert,record,report}

  optional arguments:
    -h, --help            show this help message and exit


  # record a trace
  preftrace record ./myapp args_to_my_app

  # in the same directory as the generated perf.data file
  preftrace report


==================
Installation
=================

Install with `poetry` for python.  Requires python 3.8

  poetry install
