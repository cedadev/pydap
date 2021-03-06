"""
A simple file-based Opendap server.

Serves files from a root directory, handling those recognized by installed
handlers.

"""

import re
import os
from os.path import getmtime, getsize
import time
from email.utils import formatdate

from paste.request import construct_url
from paste.httpexceptions import HTTPNotFound, HTTPSeeOther
from paste.fileapp import FileApp

from pydap.handlers.lib import get_handler, load_handlers
from pydap.lib import __version__
from pydap.exceptions import ExtensionNotSupportedError
from pydap.util.template import FileLoader, GenshiRenderer


class FileServer(object):
    def __init__(self, root, templates='templates', catalog='catalog.xml', **config):
        self.root = root.replace('/', os.path.sep)
        self.catalog = catalog

        # Regex for filtering out files and directories
        file_filter_regex = config.get('file_filter_regex')
        if file_filter_regex:
            self.file_filter = re.compile(file_filter_regex)

        # Boolean option to determines whether a hidden file or directory is served
        # Defaults to serve all, regardless of filter
        self.filter_restrict = config.get('restrict_with_filter', False)
        false_strings = {'False', 'false', '0'}
        if self.filter_restrict in false_strings:
            self.filter_restrict = False

        self.config = config

        loader = FileLoader(templates)
        self.renderer = GenshiRenderer(
                options={}, loader=loader)

        self.handlers = load_handlers()

    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        filepath = os.path.abspath(os.path.normpath(os.path.join(
                self.root,
                path_info.lstrip('/').replace('/', os.path.sep))))
        basename, extension = os.path.splitext(filepath)
        assert filepath.startswith(self.root)  # check for ".." exploit

        # try to set our renderer as the default, it none exists
        environ.setdefault('pydap.renderer', self.renderer) 

        # check for regular file or dir request
        if os.path.exists(filepath):
            # it is a file
            if os.path.isfile(filepath):
                # always serve if the file is in the static directory
                relative_filepath = os.path.relpath(filepath, self.root)
                if relative_filepath.startswith('.static' + os.path.sep):
                    pass
                # check that it is viewable according to the custom filter
                elif self.filter_restrict and self._is_hidden(filepath, True):
                    return HTTPNotFound()(environ, start_response)
		    		     
                return FileApp(filepath, content_encoding='')(environ, start_response)
            # it is a directory
            else:
                # check that it is viewable according to the custom filter
                # don't list directories beginning with a .
                if self.filter_restrict and self._is_hidden(filepath, True):
                    return HTTPNotFound()(environ, start_response)
                # return directory listing
                if not path_info.endswith('/'):
                    environ['PATH_INFO'] = path_info + '/'
                    return HTTPSeeOther(construct_url(environ))(environ, start_response)
                return self.index(environ, start_response,
                        'index.html', 'text/html')
        # else check for opendap request
        elif os.path.exists(basename):
            # Update environ with configuration keys (environ wins in case of conflict).
            for k in self.config:
                environ.setdefault(k, self.config[k])
            handler = get_handler(basename, self.handlers)
            return handler(environ, start_response)
        # check for catalog
        elif path_info.endswith('/%s' % self.catalog):
            environ['PATH_INFO'] = path_info[:path_info.rfind('/')]
            return self.index(environ, start_response,
                    'catalog.xml', 'text/xml')
        else:
            return HTTPNotFound()(environ, start_response)

    def _is_hidden(self, filepath, deep_match=False):
        '''
        Method to determine whether or not a file or directory
        should be served based on its full path
        '''
        restricted = False
        
        # Eliminate the server root from the path
        relative_filepath = os.path.relpath(filepath, self.root)
        if relative_filepath == '.':
            relative_filepath = ''
        
        if deep_match:
            # Check that any part of the path matches the filter
            filenames = relative_filepath.split(os.path.sep)
            for filename in filenames:
                if self._match_filter(filename):
                    restricted = True
        else:
            # Check that the filename matches filter
            filename = os.path.split(relative_filepath)[1]
            restricted = self._match_filter(filename)
        
        return restricted

    def _match_filter(self, filename):
        '''
        Checks a file or directory name against a provided regex
        '''
        if hasattr(self, 'file_filter'):
            if self.file_filter.search(filename):
                return True
            else:
                return False

    def index(self, environ, start_response, template_name, content_type):
        # Return directory listing.
        path_info = environ.get('PATH_INFO', '')
        directory = os.path.abspath(os.path.normpath(os.path.join(
                self.root,
                path_info.lstrip('/').replace('/', os.path.sep))))

        mtime = getmtime(directory)
        dirs_ = []
        files_ = []
        for root, dirs, files in os.walk(directory):
            # Path to make listing process more efficient by avoiding
            # recursive walk through entire directory tree
            #
            # P J Kershaw 17/11/14
            if root != directory:
                break
            
            filepaths = []
            for filename in files:
                filepath = os.path.abspath(os.path.join(root, filename))
                # Apply custom filter
                if not self._is_hidden(filepath):
                    filepaths.append(filepath)
            
            # Get Last-modified.
            filepaths = filter(os.path.exists, filepaths)  # remove broken symlinks
            if filepaths:
                mtime = max(mtime, *map(getmtime, filepaths))

            # Add list of files and directories.
            # Apply custom filter to directories and always hide directories beginning with .
            dirs_ = [d for d in dirs
                     if not self._is_hidden(os.path.abspath(os.path.join(root, d)))]
            files_ = [{
                    'name': os.path.split(filepath)[1],
                    'size': format_size(getsize(filepath)),
                    'modified': time.localtime(getmtime(filepath)),
                    'supported': supported(filepath, self.handlers),
                    } for filepath in filepaths]

        # Sort naturally using Ned Batchelder's algorithm.
        dirs_.sort(key=alphanum_key)
        files_.sort(key=lambda l: alphanum_key(l['name']))

        # Base URL.
        location = construct_url(environ, with_query_string=False)
        root = construct_url(environ, with_query_string=False, with_path_info=False).rstrip('/')

        context = {
                'environ': environ,
                'root': root,
                'location': location,
                'title': 'Index of %s' % (environ.get('PATH_INFO') or '/'),
                'dirs' : dirs_,
                'files': files_,
                'directory': directory,
                'catalog': self.catalog,
                'version': '.'.join(str(d) for d in __version__)
        }
        template = environ['pydap.renderer'].loader(template_name)
        output = environ['pydap.renderer'].render(template, context, output_format=content_type)
        last_modified = formatdate(time.mktime(time.localtime(mtime)))
        headers = [('Content-type', content_type), ('Last-modified', last_modified)]
        start_response("200 OK", headers)
        return [output.encode('utf-8')]


def supported(filepath, handlers):
    try:
        get_handler(filepath, handlers)
        return True
    except ExtensionNotSupportedError:
        return False


# http://svn.colorstudy.com/home/ianb/ImageIndex/indexer.py
def format_size(size):
    if not size:
        return 'empty'
    if size > 1024:
        size = size / 1024.
        if size > 1024:
            size = size / 1024.
            return '%.1i MB' % size
        return '%.1f KB' % size
    return '%i bytes' % size


def alphanum_key(s):
    """
    Turn a string into a list of string and number chunks.

        >>> alphanum_key("z23a")
        ['z', 23, 'a']

    From http://nedbatchelder.com/blog/200712.html#e20071211T054956

    """
    def tryint(s):
        try:
            return int(s)
        except:
            return s
    return [tryint(c) for c in re.split('([0-9]+)', s)]


def make_app(global_conf, root, templates, **kwargs):
    return FileServer(root, templates=templates, **kwargs)
