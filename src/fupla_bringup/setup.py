# ==============================================================================
# FUPLA-droneSIM: fupla_bringup package build configuration
# ==============================================================================
# This package contains only launch files - no Python nodes.
# The critical part is 'data_files': it instructs colcon to copy launch files
# into the install/ directory so 'ros2 launch' can find them.
# ==============================================================================

import os
from glob import glob
from setuptools import setup

PACKAGE_NAME = 'fupla_bringup'

setup(
    name=PACKAGE_NAME,
    version='1.0.0',
    packages=[PACKAGE_NAME],
    data_files=[
        # Register package with ament index (required for ros2 to find it)
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + PACKAGE_NAME]
        ),
        # Install package.xml (required by ROS 2 package discovery)
        (
            'share/' + PACKAGE_NAME,
            ['package.xml']
        ),
        # Install all launch files from launch/ directory.
        # glob('launch/*.launch.py') captures sim.launch.py and add_drone.launch.py
        (
            os.path.join('share', PACKAGE_NAME, 'launch'),
            glob('launch/*.launch.py')
        ),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='FUPLA Developer',
    maintainer_email='developer@fupla.dev',
    description=(
        'FUPLA-droneSIM orchestration package. '
        'Launch files for PX4 SITL multi-drone simulation environment.'
    ),
    license='Apache-2.0',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        # No executable nodes in this package - launch files only
        'console_scripts': [],
    },
)