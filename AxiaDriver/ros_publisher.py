import rospy
from geometry_msgs.msg import WrenchStamped
from std_msgs.msg import Header
from configuration import AxiaConfiguration
from data_management import Unbiasing
from udp_listener import AxiaUdpListener

'''
The AxiaRosPublisher class is responsible for publishing the data received
from the Axia sensor to ROS. It was tested to be capable of publishing at a
rate of approximately 7724 Hz, close to the maximal rate of the Axia sensor.

Each ROS message is a WrenchStamped message, published on the `/AxiaWrench` topic, with the following fields:
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
'''

class AxiaRosPublisher:
    '''
    This class is responsible for publishing the data received from the Axia
    sensor to ROS. It was tested to be capable of publishing at a rate of
    of approximately 7724 Hz, close to the maximal rate of the Axia sensor.

    '''
    def __init__(self, config: AxiaConfiguration, unbiaser: Unbiasing = None):
        '''
        Starts a UDP listener and a ROS publisher using the given configuration.

        config: The Axia configuration.
        '''
        self._config = config
        self._unbiaser = unbiaser
        self._udp_listener = AxiaUdpListener(config)
        self._publisher = rospy.Publisher('AxiaWrench', WrenchStamped, tcp_nodelay=True, queue_size=1)
        rospy.init_node('AxiaRosPublisher')

    def start(self):
        '''
        Connects to the Axia sensor and starts listening.
        '''
        self._udp_listener.connect()
        self._udp_listener.start_listening_thread(self._callback)
    
    def stop(self):
        '''
        Stops the UDP listener and disconnects from the Axia sensor.
        '''
        self._udp_listener.stop_listening_thread()
        self._udp_listener.disconnect()

    def _create_message(self, record):
        '''
        Create a ROS message from a measurement record.

        A record is a dictionary with the following keys:
        - rdt_sequence
        - ft_sequence
        - status
        - Fx
        - Fy
        - Fz
        - Tx
        - Ty
        - Tz

        Alternatively, a record can be a list with the following elements:
        [ft_sequence, Fx, Fy, Fz, Tx, Ty, Tz]

        The ft_sequence number is used to set the sequence number of the
        ROS message. The timestamp of the ROS message is set to the current
        time. The frame_id of the ROS message is set to the serial number.
        '''
        header = Header()
        header.stamp = rospy.Time.now()
        header.frame_id = self._config.current_config_serial_num
        if type(record) is dict:
            header.seq = record['ft_sequence']
            wrench = WrenchStamped()
            wrench.header = header
            wrench.wrench.force.x = record['Fx']
            wrench.wrench.force.y = record['Fy']
            wrench.wrench.force.z = record['Fz']
            wrench.wrench.torque.x = record['Tx']
            wrench.wrench.torque.y = record['Ty']
            wrench.wrench.torque.z = record['Tz']
        else:
            header.seq = record[0]
            wrench = WrenchStamped()
            wrench.header = header
            wrench.wrench.force.x = record[1]
            wrench.wrench.force.y = record[2]
            wrench.wrench.force.z = record[3]
            wrench.wrench.torque.x = record[4]
            wrench.wrench.torque.y = record[5]
            wrench.wrench.torque.z = record[6]
        return wrench

    def _callback(self, records):
        '''
        Callback function for the UDP listener. This function is called
        when new data is received from the Axia sensor.

        records: A list of measurement records as described in _create_message().
        '''
        rospy.logdebug("Got {} records".format(len(records)))
        for record in records:
            if self._unbiaser is not None:
                record = self._unbiaser.unbias_single(record)
            msg = self._create_message(record)
            rospy.logdebug("Publishing message with sequence number {}".format(msg.header.seq))
            self._publisher.publish(msg)

if __name__ == '__main__':
    config = AxiaConfiguration()
    config.load_from_yaml('Axia_Joe_Config.yaml')
    pub = AxiaRosPublisher(config)
    pub.start()
    pub._udp_listener.start_continuous_stream()
    rospy.sleep(5)
    pub._udp_listener.stop_continuous_stream()
    pub.stop()
