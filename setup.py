from setuptools import setup
from sys import version_info

setup(name='ev',
      version='0.8.8',
      description='Encrypted Vault Management Console for image stores on macOS',
      url='https://github.com/kenlowrie/ev',
      author='Ken Lowrie',
      author_email='ken@kenlowrie.com',
      license='Apache',
      packages=['ev'],
      install_requires=['kenl380.pylib'],
      entry_points = {
        'console_scripts': ['ev=ev.ev:ev_entry',
                            'ev{}=ev.ev:ev_entry'.format(version_info.major)
                           ],
      },
      zip_safe=False)
