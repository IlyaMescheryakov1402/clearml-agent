from __future__ import print_function, unicode_literals, absolute_import

import argparse
import sys
import warnings

from trains_agent.backend_api.session.datamodel import UnusedKwargsWarning

import trains_agent
from trains_agent.config import get_config
from trains_agent.definitions import FileBuffering, CONFIG_FILE
from trains_agent.helper.base import reverse_home_folder_expansion, chain_map, named_temporary_file
from trains_agent.helper.process import ExitStatus
from . import interface, session, definitions, commands
from .errors import ConfigFileNotFound, Sigterm, APIError
from .helper.trace import PackageTrace
from .interface import get_parser


def run_command(parser, args, command_name):

    debug = args.debug
    if command_name and command_name.lower() == 'config':
        command_class = commands.Config
    elif len(command_name.split('.')) < 2:
        command_class = commands.Worker
    elif hasattr(args, 'func') and getattr(args, 'func'):
        command_class = getattr(commands, command_name.capitalize())
        command_name = args.func
    else:
        command_class, command_name = command_name.split('.')
        command_class = getattr(commands, command_class.capitalize())

    args_dict = dict(vars(args))
    parser.remove_top_level_results(args_dict)

    warnings.simplefilter('ignore', UnusedKwargsWarning)

    try:
        command = command_class(**vars(args))
        get_config()['command'] = command
        debug = command._session.debug_mode
        func = getattr(command, command_name)
        return func(**args_dict)
    except ConfigFileNotFound:
        message = 'Cannot find configuration file in "{}".\n' \
                  'To create a configuration file, run:\n' \
                  '$ trains_agent init'.format(reverse_home_folder_expansion(CONFIG_FILE))
        command_class.exit(message)
    except APIError as api_error:
        if not debug:
            command_class.error(api_error)
            return ExitStatus.failure
        traceback = api_error.format_traceback()
        if traceback:
            print(traceback)
            print('Own traceback:')
        raise
    except Exception as e:
        if debug:
            raise
        command_class.error(e)
        return ExitStatus.failure
    except (KeyboardInterrupt, Sigterm):
        return ExitStatus.interrupted


def main():
    parser = get_parser()
    args = parser.parse_args()

    try:
        command_name = args.command
        if not command_name:
            return parser.print_help()
    except AttributeError:
        parser.error(argparse._('too few arguments'))

    if not args.trace:
        return run_command(parser, args, command_name)

    with named_temporary_file(
        mode='w',
        buffering=FileBuffering.LINE_BUFFERING,
        prefix='.trains_agent_trace_',
        suffix='.txt',
        delete=False,
    ) as output:
        print(
            'Saving trace for command '
            '"{definitions.PROGRAM_NAME} {command_name} {args.func}" to "{output.name}"'.format(
                **chain_map(locals(), globals())))
        tracer = PackageTrace(
            package=trains_agent,
            out_file=output,
            ignore_submodules=(__name__, interface, definitions, session))
        return tracer.runfunc(run_command, parser, args, command_name)


if __name__ == "__main__":
    sys.exit(main())