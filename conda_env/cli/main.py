# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function

import os
import sys

# pip_util.py import on_win from conda.exports
# conda.exports resets the context
# we need to import conda.exports here so that the context is not lost
# when importing pip (and pip_util)
import conda.exports  # noqa
from conda.base.context import context
from conda.cli.conda_argparse import ArgumentParser
from conda.cli.main import init_loggers
from conda.gateways.logging import initialize_logging

try:
    from conda.exceptions import conda_exception_handler
except ImportError as e:
    if 'CONDA_DEFAULT_ENV' in os.environ:
        sys.stderr.write("""
There was an error importing conda.

It appears this was caused by installing conda-env into a conda
environment.  Like conda, conda-env needs to be installed into your
base conda/Anaconda environment.

Please deactivate your current environment, then re-install conda-env
using this command:

    conda install -c conda conda-env

If you are seeing this error and have not installed conda-env into an
environment, please open a bug report at:
    https://github.com/conda/conda-env

""".lstrip())
        sys.exit(-1)
    else:
        raise e

from . import main_create
from . import main_export
from . import main_list
from . import main_remove
from . import main_update
from . import main_config


# TODO: This belongs in a helper library somewhere
# Note: This only works with `conda-env` as a sub-command.  If this gets
# merged into conda-env, this needs to be adjusted.
def show_help_on_empty_command():
    if len(sys.argv) == 1:  # sys.argv == ['/path/to/bin/conda-env']
        sys.argv.append('--help')


def create_parser():
    p = ArgumentParser()
    sub_parsers = p.add_subparsers()

    main_create.configure_parser(sub_parsers)
    main_export.configure_parser(sub_parsers)
    main_list.configure_parser(sub_parsers)
    main_remove.configure_parser(sub_parsers)
    main_update.configure_parser(sub_parsers)
    main_config.configure_parser(sub_parsers)

    show_help_on_empty_command()
    return p


def do_call(args, parser):
    relative_mod, func_name = args.func.rsplit('.', 1)
    # func_name should always be 'execute'
    from importlib import import_module
    module = import_module(relative_mod, __name__.rsplit('.', 1)[0])
    exit_code = getattr(module, func_name)(args, parser)
    return exit_code


def main():
    initialize_logging()
    parser = create_parser()
    args = parser.parse_args()
    os.environ["CONDA_AUTO_UPDATE_CONDA"] = "false"
    context.__init__(argparse_args=args)
    init_loggers(context)
    return conda_exception_handler(do_call, args, parser)


if __name__ == '__main__':
    sys.exit(main())
