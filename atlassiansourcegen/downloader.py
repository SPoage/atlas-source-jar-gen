import os
import re
import shutil
from tempfile import mkdtemp
from zipfile import ZipFile
from tarfile import TarFile
from robobrowser import RoboBrowser


# this hack makes TarFile behave identically to ZipFile. I know, I'm a bad person.
TarFile.namelist = TarFile.getnames


LOGIN_PAGE = 'https://id.atlassian.com/login'
MY_ATLASSIAN = 'https://my.atlassian.com'
SOURCE_DOWNLOAD_BASE = MY_ATLASSIAN + '/download/source'


VERSION_EXTRACT_REGEX = re.compile(r'^(?P<version>(\d+)\.(\d+)\.(\d+)?)' +
                                   r' Source \((?P<type>(ZIP|(TAR\.GZ)))( Archive)?\)$')


class AtlassianSourceDownloadError(Exception):
    pass


class AtlassianSourceArchiveError(Exception):
    def __init__(self, archive_type, *args, **kwargs):
        super().__init__("'%s' is not an accepted archive type." % archive_type, *args, **kwargs)


def select_archive_type(app, provided_type):
    archive_type = provided_type
    if isinstance(archive_type, str):
        archive_type = archive_type.lower()
    if archive_type not in ['tar', 'zip']:
        # todo: spit out warning about this
        archive_type = None
    if archive_type is None:
        # todo: verify that tarfile works on windows and default windows to zip if not
        archive_type = 'tar'
    if app == 'stash':
        # only zip archives are provided for Stash for some reason.
        archive_type = 'zip'
    return archive_type


def get_archive_extension(archive_type):
    return {'tar': 'tar.gz', 'zip': 'zip'}.get(archive_type.lower())


def get_archive_object(archive_type, archive_path):
    if archive_type == 'tar':
        return TarFile.open(archive_path, 'r:gz')
    if archive_type == 'zip':
        return ZipFile(archive_path)
    raise AtlassianSourceArchiveError("'%s' is not an accepted archive type." % archive_type)


def get_source(app, version, username, password,
               base_unpack_dir=None, clean=True, keep=True, archive_type=None):
    browser = RoboBrowser()
    # log in to the MyAtlassian portal
    browser.open(LOGIN_PAGE)
    login_form = browser.get_form(id='form-login')
    login_form['username'].value = username
    login_form['password'].value = password
    browser.submit_form(login_form)
    if browser.response.status_code != 200:
        raise IOError("Login failed to Atlassian ID service.")
    # get the list of versions for the application we're wanting to download source for
    browser.open("%s/%s" % (SOURCE_DOWNLOAD_BASE, app))
    versions = browser.select('table#source-download-table tr.smallish')
    row_number = 0
    version_download_map = {}
    archive_type = select_archive_type(app, archive_type)
    archive_extension = get_archive_extension(archive_type)
    for version_row in versions:
        row_number += 1
        try:
            columns = version_row.find_all('td')
            version_field = columns[0]
            if len(version_field) != 1:
                raise AtlassianSourceDownloadError("Version field not found.")
            version_text = version_field.text.strip()
            if len(version_text) == 0:
                raise AtlassianSourceDownloadError("Version field contained no text.")
            version_name_match = VERSION_EXTRACT_REGEX.match(version_text)
            if version_name_match is None:
                raise AtlassianSourceDownloadError("Couldn't match version number in field.")
            version_archive_type = version_name_match.group('type').lower()
            if version_archive_type != archive_extension:
                raise AtlassianSourceDownloadError("Archive type didn't match required type.")
            download_link_field = columns[-1].find('a')
            if len(download_link_field) != 1:
                raise AtlassianSourceDownloadError("Download link field not found or has multiple.")
            download_path = download_link_field.get('href').strip()
            if len(download_path) == 0:
                raise AtlassianSourceDownloadError("Download link URL contained no value.")
            version_download_map[version_name_match.group('version')] = download_path
        except AtlassianSourceDownloadError as ex:
            # print("Skipped row number %d. Reason: %s" % (row_number, ex))
            pass
    # blow up if the version requested isn't in the list
    if version not in version_download_map:
        raise AtlassianSourceDownloadError("Unable to find version '%s' on Atlassian source site."
                                           % version)
    # set the default unpack dir if it wasn't provided and create it if it doesn't exist
    if base_unpack_dir is None:
        base_unpack_dir = '%s/versions' % os.getcwd()
    else:
        base_unpack_dir = base_unpack_dir.rstrip(os.path.sep)
    os.makedirs(base_unpack_dir, exist_ok=True)
    # find the specified version in the list and download it
    version_dir_path = '%s/%s/%s' % (base_unpack_dir, app, version)
    source_archive_name = '%s/%s_%s.%s' % (base_unpack_dir, app, version, archive_extension)
    if clean and os.path.isfile(source_archive_name):
        os.unlink(source_archive_name)
    if not os.path.isfile(source_archive_name):
        source_download_url = MY_ATLASSIAN + version_download_map[version]
        browser.open(source_download_url)
        with open(source_archive_name, 'wb') as source_archive_file:
            source_archive_file.write(browser.response.content)
    with get_archive_object(archive_type, source_archive_name) as src:
        os.makedirs(version_dir_path, exist_ok=True)
        top_dirs = list(set(d.split(os.path.sep)[0] for d in src.namelist()))
        if len(top_dirs) != 1:
            raise AtlassianSourceDownloadError("Couldn't unpack archive - unexpected contents.")
        # extract the archive to a temporary location that we can move from later if all goes well
        top_level_dir_name = top_dirs[0]
        archive_extraction_dir = mkdtemp()
        try:
            # unpack the archive to the temporary folder
            src.extractall(archive_extraction_dir)
            # remove the target directory if it already exists
            if os.path.isdir(version_dir_path):
                shutil.rmtree(version_dir_path)
            shutil.move(os.path.join(archive_extraction_dir, top_level_dir_name), version_dir_path)
        finally:
            shutil.rmtree(archive_extraction_dir)
    if not keep:
        os.unlink(source_archive_name)
    # now that we've got the source, return the path it lives at
    return version_dir_path