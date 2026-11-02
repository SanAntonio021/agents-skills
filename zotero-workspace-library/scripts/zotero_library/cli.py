import argparse
import json
import sys

from . import connection
from .client import Client
from .errors import LibraryError
from .operations import Executor, Store, summary
from .request import read_request


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'status' and '--capabilities' not in argv:
        return connection.main(argv)
    parser = argparse.ArgumentParser(description='Shared Zotero commands (JSON output)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'find', 'get', 'collections', 'archive', 'prune', 'operation'):
        p = sub.add_parser(name)
        for option in ('profile', 'base-url', 'policy', 'state-dir'):
            p.add_argument('--' + option)
        p.add_argument('--timeout', type=float, default=3)
        p.add_argument('--json', action='store_true')
        if name == 'status':
            p.add_argument('--capabilities', action='store_true')
        if name in ('find', 'get', 'collections'):
            p.add_argument('--group', type=int)
        if name == 'find':
            p.add_argument('--query', default='')
            p.add_argument('--doi')
            p.add_argument('--request')
        if name == 'get':
            p.add_argument('--key', required=True)
        if name in ('archive', 'prune'):
            p.add_argument('--request', required=True)
        if name == 'operation':
            p.add_argument('action', choices=('status', 'resume'))
            p.add_argument('--id', required=True)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 10:
        parser.error('timeout must be greater than zero and no more than 10 seconds')
    if getattr(args, 'group', None) is not None and args.group <= 0:
        parser.error('group must be positive')
    try:
        client = Client(args.profile, args.base_url, args.timeout, args.policy)
        library = {'type': 'group', 'id': args.group} if getattr(args, 'group', None) else {'type': 'user'}
        if args.command == 'status':
            result = dict(client.status)
            try:
                result['write_capabilities'] = client.native({'action': 'capabilities'})
                client.prepare({})
                result['automatic_fetch_protection_ready'] = True
            except LibraryError as error:
                result['automatic_fetch_protection_ready'] = False
                result['write_error'] = error.code
        elif args.command == 'find':
            result = client.resolve(read_request(args.request)) if args.request else client.find(library, args.query, args.doi)
        elif args.command == 'get':
            result = client.get(library, args.key)
        elif args.command == 'collections':
            result = client.collections(library)
        else:
            executor = Executor(client, Store(args.state_dir))
            if args.command == 'operation':
                receipt = executor.status(args.id) if args.action == 'status' else executor.resume(args.id)
            else:
                receipt = executor.run(read_request(args.request, args.command), args.command)
            result = summary(receipt)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0 if args.command in ('status', 'find', 'get', 'collections') or result.get('state') == 'completed' else 2
    except LibraryError as error:
        print(json.dumps({'error': error.code}))
        return 1
    except Exception:
        print(json.dumps({'error': 'library_command_failed'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
