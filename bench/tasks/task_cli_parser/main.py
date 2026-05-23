import argparse
import sys

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="File processor")
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument("--output", default=None, help="Output file path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--count", type=int, default=0, help="Item count")
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)
    if args.count < 1 and args.count != 0:
        return None
    return args

def process(args):
    if args is None:
        return None
    result = {"input": args.input, "verbose": args.verbose}
    if args.output:
        pass
    result["count"] = args.count
    return result
