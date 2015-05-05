import os
import tempfile
import traceback
from pkg_resources import resource_string
from mavpy import Maven, get_maven_name, env_var
from argparse import ArgumentParser, ArgumentTypeError, ArgumentError
from distutils.version import StrictVersion
from atlassiansourcegen.downloader import get_source


VALID_APPS = ['crowd', 'jira', 'confluence', 'stash', 'bamboo', 'fisheye', 'crucible']
APP_BUILD_DIRS = {'jira':       'jira-project',
                  'confluence': 'confluence-project',
                  'stash':      'stash-parent'}


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
    arg_parser.add_argument('app', type=check_atlassian_app,
                            help="The name of the app to generate source for.")
    arg_parser.add_argument('version', type=check_semantic_version,
                            help="The version of the app to generate source for.")
    # flag-specified arguments
    arg_parser.add_argument('-u', '--username', required=True,
                            help="The username to use for the Atlassian source download site.")
    arg_parser.add_argument('-p', '--password', required=True,
                            help="The password to use for the Atlassian source download site.")
    arg_parser.add_argument('-q', '--quiet', action='store_true', default=False,
                            help="Suppress SDK output unless a problem occurs.")
    arg_parser.add_argument('-S', '--sdk-path', required=True,
                            help="Path to the Atlassian SDK base folder.")
    arg_parser.add_argument('-c', '--clean', action='store_true', default=False,
                            help="Force the downloader to re-download the source zip.")
    arg_parser.add_argument('-C', '--clean-build', action='store_true', default=False,
                            help="Run 'clean' before building the source. Shouldn't be necessary.")
    arg_parser.add_argument('-x', '--discard-source', action='store_false', default=True,
                            help="Force the downloader to remove the source archive once unpacked.")
    arg_parser.add_argument('-d', '--source-dir', default=os.getcwd(),
                            help="Download the source into the specified base directory.")
    arg_parser.add_argument('-R', '--repo', default=None,
                            help="The URL to an artifact repository to use for dependencies.")
    arg_parser.add_argument('-D', '--deploy-repo', default=None,
                            help="The URL to an artifact repository to deploy the source JARs to.")
    arg_parser.add_argument('-U', '--repo-user', default=None,
                            help="The user to log in as if the artifact repository requires login.")
    arg_parser.add_argument('-P', '--repo-pass', default=None,
                            help="The password to use if the artifact repository requires login.")
    arg_parser.add_argument('-n', '--no-deploy', default=False,
                            help="Don't deploy the source JARs to the artifact repository.")
    args = arg_parser.parse_args()
    if args.repo is not None:
        if args.repo_user != args.repo_pass and None in [args.repo_user, args.repo_pass]:
            raise ArgumentError('--repo-user',
                                'Must provide both --repo-user and --repo-pass, or neither.')
    return args


def make_settings_file(username=None, password=None):
    _, file_path = tempfile.mkstemp(prefix='deployment_settings_', suffix='.xml', text=True)
    settings_file = resource_string('atlassiansourcegen', 'resources/deploy-settings.xml')
    settings_file = settings_file.decode("utf-8")
    if username is not None:
        settings_file = settings_file.replace('ATLAS_ARTIFACT_REPO_USER', username)
    if password is not None:
        settings_file = settings_file.replace('ATLAS_ARTIFACT_REPO_PASS', password)
    with open(file_path, 'w') as handle:
        handle.write(settings_file)
    return file_path


def build_source(atlas_maven, app, clean_build=False):
    build_targets = ['source:jar', 'install']
    if clean_build:
        build_targets.insert(0, 'clean')
    if app == 'confluence':
        atlas_maven.disable_soke = None
        atlas_maven.disable_studio = None
        atlas_maven.disable_cluster = None
    return atlas_maven(*build_targets)


def deploy_source_jars(atlas_maven, app, target_repo):
    atlas_maven.skip_nexus_staging = None
    atlas_maven.altDeploymentRepository = 'atlas-source-repo::default::%s' % target_repo
    return atlas_maven('deploy')


def run():
    args = get_cmdline_args()
    src_dir = get_source(args.app, args.version, args.username, args.password,
                         base_unpack_dir=args.source_dir, clean=args.clean,
                         keep=args.discard_source)
    settings_path = None
    build_success = False
    maven_dirs = [os.path.join(src_dir, d) for d in os.listdir(src_dir) if d.startswith('maven')]
    atlas_maven_path = os.path.sep.join([args.sdk_path, 'bin', 'atlas-mvn'])
    try:
        settings_path = make_settings_file(args.repo_user, args.repo_pass)
        # should try newer maven versions first and fall back to older ones if it the new ones fail
        for maven_dir in reversed(sorted(maven_dirs)):
            try:
                # should contain only one directory - assumption may prove incorrect
                maven_real_dir = os.path.join(maven_dir.rstrip(os.path.sep), os.listdir(maven_dir)[0])
                maven_bin_path = os.path.join(maven_real_dir, 'bin', get_maven_name())
                with env_var('ATLAS_MVN', maven_bin_path):
                    maven = Maven(atlas_maven_path, os.path.join(src_dir, APP_BUILD_DIRS[args.app]))
                    maven.options('-s %s' % settings_path, '-U')
                    maven.skipTests = 'true'
                    maven.maven_test_skip = 'true'
                    build_result = build_source(maven, args.app, clean_build=args.clean_build)
                    if not args.quiet:
                        print(build_result.output)
                    if build_result.exit_code != 0:
                        raise Exception("Build failed!")
                    if not args.no_deploy:
                        deploy_repo = args.repo if args.deploy_repo is None else args.deploy_repo
                        deploy_result = deploy_source_jars(maven, args.app, deploy_repo)
                        if not args.quiet:
                            print(deploy_result.output)
                        if deploy_result.exit_code != 0:
                            raise Exception("Deployment failed!")
                    build_success = True
                    break
            except Exception:
                print(traceback.format_exc())
    finally:
        if settings_path is not None:
            os.unlink(settings_path)
    if not build_success:
        raise RuntimeError("No Maven versions present in source directory resulted in good build.")
    print("Complete!")