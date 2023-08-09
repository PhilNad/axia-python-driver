# ATI Axia Python Driver and Tools
This repository contains Python modules for the communication, configuration, and use of the ATI Axia line of Force-Torque sensors equipped with an Ethernet interface. 

## Installation
The following dependencies are required:

### Dependencies
- Python 3.7+
- SciPy (for the Savitzky-Golay filter)
- NumPy
- telnetlib3
- rospy (for publishing ROS messages)
- PyYAML

## Usage
To use a sensor, the one information you cannot do without is its IP address. If you do not have this information then you will need to find it by [scanning the network](https://nmap.org/book/man-host-discovery.html). Once you have the IP address, you can connect to the sensor with:
```python
sensor_ip = '192.168.3.101'
com = AxiaCommunication(sensor_ip)
com.connect()
```
and retrieve the current configuration with
```python
config = com.read_configuration()
```
The configuration is represented by an AxiaConfiguration object, which can be saved to a YAML file with
```python
config.save_to_yaml('current_config.yaml')
```
It is good practice not to assume that the sensor is in a known state when you connect to it. Therefore, it is recommended to load a saved/working configuration before starting to use the sensor. This can be done with
```python
config = AxiaConfiguration.load_from_yaml('Axia_Joe_Config.yaml')
com.write_configuration(config)
```
which will write your pre-defined settings to the sensor, but **will not save them permanently**. To save the settings permanently, you can use
```python
com.write_configuration(config)
com.write_settings_to_memory()
```
but that is never necessary for the operation of the sensor, and its good practice to avoid it unless you have a good reason to do so.

Although you will usually want to receive data through ROS or the Recorder, you can also receive data directly from the sensor by first defining a callback function
```python
def cb(records):
        for rec in records:
            print('Fx: {}, Fy: {}, Fz: {}, Tx: {}, Ty: {}, Tz: {}'.format(rec['Fx'], rec['Fy'], rec['Fz'], rec['Tx'], rec['Ty'], rec['Tz']))
```
and then starting a UDP listening thread with 
```python
udp = AxiaUdpListener(config)
udp.connect()
udp.start_listening_thread(cb)
udp.send_records(5)
time.sleep(5)
udp.stop_listening_thread()
udp.disconnect()
```
for some time during which the callback function will be called whenever data is received. It is good practice to stop the listening thread and disconnect from the sensor when you are done with it such that other processes can use it.

In the above example, it was requested to send a fixed number of measurements/records by the `idp.send_records(5)` command. This is called batch mode. Alternatively, you can request the sensor to send data continuously by using
```python
udp.start_continuous_stream()
time.sleep(5)
udp.stop_continuous_stream()
```
during which the sensor will send data at the frequency specified in the configuration (rdtrate setting).

Alternatively, you can spawn a ROS publisher with
```python
config = AxiaConfiguration()
config.load_from_yaml('Axia_Joe_Config.yaml')
pub = AxiaRosPublisher(config)
pub.start()
pub._udp_listener.start_continuous_stream()
time.sleep(5)
pub._udp_listener.stop_continuous_stream()
pub.stop()
```
which will publish the data to the `/AxiaWrench` topic. Note that the ROS publisher will automatically start and stop the UDP listening thread, so you do not need to do that yourself.

The rate of data published on the ROS topic can be monitored with
```bash
rostopic hz /AxiaWrench
```
such that you have an idea of the impact of data processing on the rate of data publication.

Finally, you can use the Recorder class to record data to a CSV file with
```python
config = AxiaConfiguration()
config.load_from_yaml('Axia_Joe_Config.yaml')
filter = Filtering.MovingAverageFilter(window_length=8)
recorder = Recorder('output.csv', config, filter=filter, ros_publish=True)
recorder.start_recording()
time.sleep(5)
recorder.stop_recording()
```
which will record data to the output.csv file, with a moving average filter applied to the data, and with the data published to the `/AxiaWrench` ROS topic. Note that the Recorder class will automatically start and stop the UDP listening thread, so you do not need to do that yourself.


## Modules
### Data Management
The data management module contains classes for recording, filtering, and saving
data received from the Axia sensor. A Recorder object can be used to record data
and save it to disk (either as a CSV or a PKL file), with the possibility of filtering and/or unbiasing the data
before saving it. The Recorded can spawn a ROS publisher can be used to publish 
the data to the `AxiaWrench` ROS topic.

Note that the compute time involved in filtering and unbiasing the data is
significant and will reduce the rate at which data can be recorded. If possible
it is recommended to record the data without filtering or unbiasing, and then
perform these operations offline.

### ROS Publisher
The AxiaRosPublisher class is responsible for publishing the data received
from the Axia sensor to ROS. It was tested to be capable of publishing at a
rate of approximately 7724 Hz, close to the maximal rate of the Axia sensor.

Each ROS message is a [WrenchStamped message](http://docs.ros.org/en/api/geometry_msgs/html/msg/WrenchStamped.html), published on the `/AxiaWrench` topic, with the following fields:
- header
    - seq: The sequence number of the measurement record.
    - stamp: The timestamp of the measurement record.
    - frame_id: The serial number of the Axia sensor.
- wrench
    - force
        - x: The x component of the force.
        - y: The y component of the force.
        - z: The z component of the force.
    - torque
        - x: The x component of the torque.
        - y: The y component of the torque.
        - z: The z component of the torque.

### UDP Listener
The AxiaUdpListener class listens to the UDP port of the Axia sensor and
calls a callback function whenever data is received. The callback function
is called with a list of measurement records. This class can also be used
to trigger the Axia sensor to send (or stop sending) data. Two types of modes are supported:
- Continuous mode: The Axia sensor continuously sends data at a fixed rate.
- Batch mode: The Axia sensor sends a fixed number of records and then stops.

At the maximum sampling rate of 7.8 kHz, the sensor can stream about 4.5 Mbps
of data, generating about 10 MB/min of data on the disk when encoded in
binary with no overhead.

### Communication
The AxiaCommunication class is used to communicate with the Axia sensor
over telnet. It can be used to read/write sensor's settings either
temporarily or permanently. It can also be used to read the sensor's
status and version.

### Configuration
The AxiaConfiguration class is used to represent a specific configuration
of the Axia sensor, which can be loaded and saveed in YAML files. The default configuration of the sensor is stored in the `factory_configuration.yaml` file.

## Limitations
- For now, only the Ethernet interface is supported, although it would be easy to add support for the RS485 serial interface.
