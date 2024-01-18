from setuptools import setup

setup(
    name='axia-python-driver',
    version='0.0.1',
    description='A simple independant Python driver for the ATI Axia Force-Torque sensor.',
    author='Philippe Nadeau',
    author_email='philippe.nadeau@robotics.utias.utoronto.ca',
    license='MIT',
    packages=['AxiaDriver'],
    install_requires=['telnetlib3', 'rospy', 'PyYAML', 'scipy', 'numpy'],
    python_requires=">=3.8",
    include_package_data=True
)
