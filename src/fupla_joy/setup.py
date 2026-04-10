# ==============================================================================
# FUPLA-droneSIM: fupla_joy package build configuration
# ==============================================================================
# This package provides two executable ROS 2 nodes:
#   - node_joy_to_rc : Futaba T8J -> MAVLink RC_CHANNELS_OVERRIDE
#   - stream_to_qgc  : ROS 2 Image -> H.264/RTP -> QGroundControl UDP
#
# Entry points under 'console_scripts' allow running nodes with:
#   ros2 run fupla_joy node_joy_to_rc
#   ros2 run fupla_joy stream_to_qgc
# ==============================================================================

import os
from glob import glob
from setuptools import find_packages, setup

PACKAGE_NAME = 'fupla_joy'

setup(
    name=PACKAGE_NAME,
    version='1.0.0',
    # find_packages() automatically discovers fupla_joy/ (contains __init__.py)
    packages=find_packages(exclude=['test']),
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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='FUPLA Developer',
    maintainer_email='developer@fupla.dev',
    description=(
        'FUPLA-droneSIM joystick and video streaming nodes. '
        'Futaba T8J RC transmitter support and QGroundControl video bridge.'
    ),
    license='Apache-2.0',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            # Format: 'executable_name = package.module:function'
            'node_joy_to_rc = fupla_joy.node_joy_to_rc:main',
            'stream_to_qgc  = fupla_joy.stream_to_qgc:main',
            'node_joy_diag = fupla_joy.node_joy_diag:main',
        ],
    },
)