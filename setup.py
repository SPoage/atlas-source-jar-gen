#!/usr/bin/env python
from setuptools import setup, find_packages


setup(name='atlassiansourcegen',
      version='0.1.0',
      description='Atlassian Source JAR Generation Utility',
      classifiers=['Development Status :: 2 - Pre-Alpha',
                   'Environment :: Console',
                   'Intended Audience :: Developers',
                   'Intended Audience :: System Administrators',
                   'License :: OSI Approved :: IBM Public License',
                   'Operating System :: POSIX :: Linux',
                   'Programming Language :: Python :: 3.4',
                   'Programming Language :: Java',
                   'Topic :: Software Development :: Build Tools'],
      url='https://github.com/SPoage/atlas-source-jar-gen',
      author='Shane Poage',
      packages=find_packages(),
      entry_points={'console_scripts': ['atlas-source-gen=atlassiansourcegen.main:run']},
      install_requires=['mavpy', 'robobrowser'])