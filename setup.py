from setuptools import setup, find_packages

try:
    from pydap.lib import __version__
except ImportError:
    __version__ = ('unknown',)

install_requires=[
    'numpy',
    'httplib2>=0.4.0',
    'Genshi',
    'Paste',
    'PasteScript',
    'PasteDeploy',
],

setup(name='Pydap',
      version='.'.join(str(d) for d in __version__),
      description="An implementation of the Data Access Protocol.",
      long_description="",
      classifiers=[
            "Programming Language :: Python :: 2",
            "Programming Language :: Python :: 2.7",
            ],
      keywords='opendap dods dap science data',
      author='Roberto De Almeida',
      author_email='rob@pydap.org',
      url='http://pydap.org/',
      license='MIT',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      namespace_packages=["pydap", "pydap.responses",
                          "pydap.handlers", "pydap.wsgi"],
      install_requires=install_requires,
      extras_require={
            'test': ['nose', 'wsgi_intercept'],
            'docs': ['Paver', 'Sphinx', 'Pygments', 'coards'],
            'esgf': ['M2Crypto'],
      },
      test_suite="nose.collector",
      entry_points="""
            [pydap.response]
            dds = pydap.responses.dds:DDSResponse
            das = pydap.responses.das:DASResponse
            dods = pydap.responses.dods:DODSResponse
            asc = pydap.responses.ascii:ASCIIResponse
            ascii = pydap.responses.ascii:ASCIIResponse
            ver = pydap.responses.version:VersionResponse
            version = pydap.responses.version:VersionResponse
            help = pydap.responses.help:HelpResponse
            html = pydap.responses.html:HTMLResponse
      
            [paste.app_factory]
            server = pydap.wsgi.file:make_app
      
            [paste.paster_create_template]
            pydap = pydap.wsgi.templates:DapServerTemplate
      """)