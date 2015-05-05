import os
import traceback
from distutils.version import StrictVersion
from argparse import ArgumentParser, ArgumentTypeError
from atlassiansourcegen.downloader import get_source
from mavpy import Maven, get_maven_name


VALID_APPS = ['crowd', 'jira', 'confluence', 'stash', 'bamboo', 'fisheye', 'crucible']


def check_semantic_version(value):
    try:
        StrictVersion(value)
        return value
    except ValueError:
        raise ArgumentTypeError("Invalid version number: %s" % value)


def check_atlassian_app(value):
    value = value.lower()
    if value not in VALID_APPS:
        raise ArgumentTypeError("'%s' is not a valid Atlassian application." % value)
    return value


def get_cmdline_args():
    arg_parser = ArgumentParser()
    # positional arguments
    arg_parser.add_argument('application', type=check_atlassian_app,
                            help="The name of the app to generate source for.")
    arg_parser.add_argument('version', type=check_semantic_version,
                            help="The version of the app to generate source for.")
    # flag-specified arguments
    arg_parser.add_argument('-u', '--username', required=True,
                            help="The username to use for the Atlassian source download site.")
    arg_parser.add_argument('-p', '--password', required=True,
                            help="The password to use for the Atlassian source download site.")
    arg_parser.add_argument('-q', '--quiet', action='store_true', default=False,
                            help="Suppress Maven output and only show end results output.")
    arg_parser.add_argument('-c', '--clean', action='store_true', default=False,
                            help="Force the downloader to re-download the source zip.")
    arg_parser.add_argument('-r', '--discard', action='store_false', default=True,
                            help="Force the downloader to discard the source zip once unpacked.")
    arg_parser.add_argument('-d', '--source-dir', default=os.getcwd(),
                            help="Download the source into the specified base directory.")
    return arg_parser.parse_args()


def run():
    args = get_cmdline_args()
    src_dir = get_source(args.application, args.version, args.username, args.password,
                         base_unpack_dir=args.source_dir, clean=args.clean, keep=args.discard)
    maven_dirs = [os.path.join(src_dir, d) for d in os.listdir(src_dir) if d.startswith('maven')]
    build_success = False
    # should try newer maven versions first and fall back to older ones if it the new ones fail
    for maven_dir in reversed(sorted(maven_dirs)):
        try:
            # should contain only one directory - assumption may prove incorrect
            maven_real_dir = os.path.join(maven_dir.rstrip(os.path.sep), os.listdir(maven_dir)[0])
            maven_bin_path = os.path.join(maven_real_dir, 'bin', get_maven_name())
            print(maven_bin_path)
            maven = Maven(maven_bin_path, src_dir)
            maven('clean', 'source:jar', maven_test_skip='true', skipTests='true')
            build_success = True
            break
        except Exception as e:
            # print the exception but otherwise let it continue. will fail at end if nothing works
            print(traceback.format_exc())
    if not build_success:
        raise RuntimeError("No Maven versions present in source directory resulted in good build.")
    print("Complete!")