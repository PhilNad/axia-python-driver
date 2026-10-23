from glob import glob

from setuptools import setup

package_name = "axia_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="Miguel Rogel",
    maintainer_email="miguel.rogel.servicios@gmail.com",
    description="ROS 2 node for the ATI Axia80 F/T sensor",
    license="MIT",
    entry_points={"console_scripts": [
        "axia_node = axia_ros2.axia_node:main",
        "axia_cli = axia_ros2.cli:main",
        "fake_sensor = axia_ros2.fake_sensor:main",
    ]},
)
