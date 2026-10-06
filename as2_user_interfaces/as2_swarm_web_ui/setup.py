import os
from glob import glob
from setuptools import setup

package_name = 'as2_swarm_web_ui'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        (os.path.join('share', package_name, 'static'), glob('static/*')),
        (os.path.join('share', package_name, 'config'), glob('config/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='myamazum',
    maintainer_email='27220996+myamazum@users.noreply.github.com',
    description='Browser-based fleet status and group command interface for Aerostack2.',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'swarm_web_ui = as2_swarm_web_ui.server:main',
        ],
    },
)
