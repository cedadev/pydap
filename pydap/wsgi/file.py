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
    def __init__(self, root, templates='templates', catalog='catalog.xml',
                 file_filter_regex=None, **config):
        self.root = root.replace('/', os.path.sep)
        self.catalog = catalog
        
        if file_filter_regex is not None:
            self.file_filter = re.compile(file_filter_regex)
        else:
            self.file_filter = None
        
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
            # check that it is viewable according to the custom filter
            filename = os.path.split(filepath.rstrip(os.path.sep))[1]
            if self.is_filtered(filename):
                return HTTPNotFound()(environ, start_response)

            elif os.path.isfile(filepath):
                return FileApp(filepath)(environ, start_response)
            else:
                # don't list directories beginning with a .
                if filename.startswith('.'):
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
            
            # Apply custom filter to files.
            filtered_files = [filename for filename in files
                     if not self.is_filtered(filename)]
            
            filepaths = [ 
                    os.path.abspath(os.path.join(root, filename))
                    for filename in filtered_files ]
            # Get Last-modified.
            filepaths = filter(os.path.exists, filepaths)  # remove broken symlinks
            if filepaths:
                mtime = max(mtime, *map(getmtime, filepaths))

            # Add list of files and directories.
            # Apply custom filter to directories and always hide directories beginning with .
            dirs_ = [d for d in dirs
                     if not self.is_filtered(d) and not d.startswith('.')]
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
                'catalog': self.catalog,
                'version': '.'.join(str(d) for d in __version__)
        }
        template = environ['pydap.renderer'].loader(template_name)
        output = environ['pydap.renderer'].render(template, context, output_format=content_type)
        last_modified = formatdate(time.mktime(time.localtime(mtime)))
        headers = [('Content-type', content_type), ('Last-modified', last_modified)]
        start_response("200 OK", headers)
        return [output.encode('utf-8')]
    
    def is_filtered(self, filename):
        '''
        Checks whether the file has been filtered out according to the custom filter.
        '''
        filtered = False
        
        if self.file_filter is not None:
            if self.file_filter.match(filename):
                filtered = True
                
        return filtered


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
