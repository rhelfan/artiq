#!/usr/bin/env python3

import argparse

from artiq.devices.pdq2.driver import Pdq2
from artiq.protocols.pc_rpc import simple_server_loop
from artiq.tools import verbosity_args, init_logger, simple_network_args


def get_argparser():
    parser = argparse.ArgumentParser(description="PDQ2 controller")
    simple_network_args(parser, 3252)
    parser.add_argument(
        "-s", "--serial", default=None,
        help="device (FT245R) serial string [first]")
    parser.add_argument(
        "-d", "--debug", default=False, action="store_true",
        help="debug communications")
    verbosity_args(parser)
    return parser


def main():
    args = get_argparser().parse_args()
    init_logger(args)

    dev = Pdq2(serial=args.serial)
    try:
        simple_server_loop({"pdq2": dev}, args.bind, args.port,
                           id_parameters="serial=" + str(args.serial))
    finally:
        dev.close()

if __name__ == "__main__":
    main()
