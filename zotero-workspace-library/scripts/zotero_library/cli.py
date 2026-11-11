import argparse
import json
import sys
from pathlib import Path

from . import connection
from .client import Client
from .errors import LibraryError
from .operations import Executor, Store, summary
from .request import read_request
from .objects import plan_collection_update
from .citations import export_bib, cite
from .reading import read_pdf, search


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description='Shared Zotero commands (JSON output)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('status', 'find', 'get', 'collections', 'archive', 'prune', 'collection', 'operation',
                 'export', 'cite', 'read', 'search'):
        p = sub.add_parser(name)
        for option in ('profile', 'base-url', 'policy', 'state-dir'):
            p.add_argument('--' + option)
        p.add_argument('--timeout', type=float, default=3)
        p.add_argument('--json', action='store_true')
        if name == 'status':
            p.add_argument('--capabilities', action='store_true')
        if name in ('find', 'get', 'collections', 'export', 'read', 'search'):
            p.add_argument('--group', type=int)
        if name == 'find':
            p.add_argument('--query', default='')
            p.add_argument('--doi')
            p.add_argument('--request')
        if name in ('get', 'read'):
            p.add_argument('--key', required=True)
        if name in ('archive', 'prune', 'cite'):
            p.add_argument('--request', required=True)
        if name == 'collection':
            p.add_argument('action', choices=('plan', 'update'))
            p.add_argument('--request', required=True)
        if name == 'export':
            p.add_argument('--keys', nargs='+', required=True)
            p.add_argument('--output')
        if name == 'read':
            p.add_argument('--attachment')
            p.add_argument('--pages')
            p.add_argument('--max-chars', type=int, default=30000)
        if name == 'search':
            p.add_argument('--query', required=True)
            p.add_argument('--scope', choices=('all', 'notes', 'annotations', 'fulltext'), default='all')
            p.add_argument('--limit', type=int, default=100)
        if name == 'operation':
            p.add_argument('action', choices=('status', 'resume'))
            p.add_argument('--id', required=True)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 10:
        parser.error('timeout must be greater than zero and no more than 10 seconds')
    if getattr(args, 'group', None) is not None and args.group <= 0:
        parser.error('group must be positive')
    try:
        if args.command == 'status':
            result = connection.status_payload(args.profile, args.base_url, args.timeout)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result['read_only_ready'] else 1
        if args.command == 'collection':
            request = read_request(args.request, 'collection')
            client = Client(args.profile, args.base_url, args.timeout, args.policy)
            if args.action == 'plan':
                result = plan_collection_update(client, request)
                print(json.dumps(result, ensure_ascii=True, indent=2))
                return 0
            result = summary(Executor(client, Store(args.state_dir)).run(request, 'collection'))
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if result.get('state') == 'completed' else 2
        client = Client(args.profile, args.base_url, args.timeout, args.policy)
        library = {'type': 'group', 'id': args.group} if getattr(args, 'group', None) else {'type': 'user'}
        if args.command == 'find':
            result = client.resolve(read_request(args.request)) if args.request else client.find(library, args.query, args.doi)
        elif args.command == 'get':
            result = client.get(library, args.key)
        elif args.command == 'collections':
            result = client.collections(library)
        elif args.command == 'export':
            result = export_bib(client, library, args.keys, args.output)
        elif args.command == 'cite':
            try:
                raw = Path(args.request).read_bytes()
                if len(raw) > 1024 * 1024:
                    raise LibraryError('citation_request_too_large')
                request = json.loads(raw.decode('utf-8-sig'))
            except (OSError, ValueError, UnicodeError):
                raise LibraryError('citation_request_unreadable') from None
            result = cite(client, request)
        elif args.command == 'read':
            result = read_pdf(client, library, args.key, args.pages, args.attachment, args.max_chars)
        elif args.command == 'search':
            result = search(client, library, args.query, args.scope, args.limit)
        else:
            executor = Executor(client, Store(args.state_dir))
            if args.command == 'operation':
                receipt = executor.status(args.id) if args.action == 'status' else executor.resume(args.id)
            else:
                receipt = executor.run(read_request(args.request, args.command), args.command)
            result = summary(receipt)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.command in ('status', 'find', 'get', 'collections', 'search'):
            return 0
        return 0 if result.get('state') in ('completed', 'exported', 'cited', 'read') else 2
    except LibraryError as error:
        result = {**connection.empty_status(), 'error': error.code} if args.command == 'status' else {'error': error.code}
        print(json.dumps(result))
        return 1
    except Exception:
        if args.command == 'status':
            print(json.dumps({**connection.empty_status(), 'error': 'status_check_failed'}))
        else:
            print(json.dumps({'error': 'library_command_failed'}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
