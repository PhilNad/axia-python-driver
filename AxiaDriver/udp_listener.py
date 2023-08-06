import logging
import socket
import time
import threading
from configuration import AxiaConfiguration


class AxiaUdpListener:
    def __init__(self, axia_config: AxiaConfiguration):
        self._logger = logging.getLogger(__name__)
        self._port       = axia_config.udp_port
        self._ip_address = axia_config.ip_address
        self._location   = axia_config.location
        self._status     = axia_config.is_good_status
        self._data_size  = 36*(axia_config.udp_records_per_packet)
        self._data_freq  = axia_config.udp_transmit_rate
        self._cpf        = axia_config.counts_per_force
        self._cpt        = axia_config.counts_per_torque
        self._connected  = False

    def connect(self):
        '''
        Connects to the Axia sensor.
        '''
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._logger.info("Connected to {}:{} @ {} (Good Status = {})".format(self._ip_address, self._port, self._location, self._status))
        self._connected = True

    def disconnect(self):
        '''
        Disconnects from the Axia sensor.
        '''
        self._logger.info("Disconnected from {}:{} @ {} (Good Status = {})".format(self._ip_address, self._port, self._location, self._status))
        self._socket.close()
        self._connected  = False

    def start_listening_thread(self, callback=None):
        '''
        Starts a thread that listens to the UDP port and calls the
        callback function whenever data is received.
        '''
        self._callback = callback
        self._stop_thread = False
        self._thread = threading.Thread(target=self._listen)
        self._thread.daemon = True
        self._thread.start()
    
    def _listen(self):
        '''
        Listens to the UDP port and calls the callback function whenever
        data is received.
        '''
        if not self._connected:
            self.connect()

        while not self._stop_thread:
            data = self._read()
            records = self._parse_data(data)
            if self._callback is not None:
                self._callback(records)
            logging.debug("Got {} records".format(len(records)))

        #Stop and reset the callback
        self._thread.join()
        self._callback = None

    def stop_listening_thread(self):
        '''
        Stops the thread that listens to the UDP port.
        '''
        self._stop_thread = True

    def _parse_data(self, data: bytes):
        '''
        Parses the data received from the UDP port. The data is assumed to
        be a sequence of measurement records.

        Returns a list of measurement records. Each record is a dictionary
        with the keys corresponding to the fields in the record. The force
        and torque values are expressed in their respective physical units.

        Each measurement record contains 9*32 = 36 bytes of data:
        - Uint32 rdt_sequence
        - Uint32 ft_sequence
        - Uint32 status
        - Int32 Fx
        - Int32 Fy
        - Int32 Fz
        - Int32 Tx
        - Int32 Ty
        - Int32 Tz
        and there is no separator between the records when more than
        one record is transmitted in one packet.
        '''
        record_size = 36
        record_count = int(len(data)/record_size)
        records = []
        for i in range(record_count):
            record = {}
            record['rdt_sequence'] = int.from_bytes(data[0:4], 'big')
            record['ft_sequence']  = int.from_bytes(data[4:8], 'big')
            record['status']       = int.from_bytes(data[8:12], 'big')
            record['Fx']           = int.from_bytes(data[12:16], 'big', signed=True) / self._cpf
            record['Fy']           = int.from_bytes(data[16:20], 'big', signed=True) / self._cpf
            record['Fz']           = int.from_bytes(data[20:24], 'big', signed=True) / self._cpf
            record['Tx']           = int.from_bytes(data[24:28], 'big', signed=True) / self._cpt
            record['Ty']           = int.from_bytes(data[28:32], 'big', signed=True) / self._cpt
            record['Tz']           = int.from_bytes(data[32:36], 'big', signed=True) / self._cpt
            records.append(record)
            data = data[record_size:]
        return records

    def _read(self):
        '''
        Reads data from the socket. More than one measurement record may be
        contained in the data. Since the maximal amount of data that can be
        transmitted in one UDP packet is 65499 bytes, the maximal number of
        measurement records that can be transmitted in one packet is 1819.

        Sending multiple records in one packet will create a delay between
        the measurement time and the reception time, but can reduce the
        bandwidth by about 50% as a single header is used for all records.

        At the maximal rate of 7812 Hz, the UDP stream will consume 
        4.3 Mbps of bandwidth, which is not that much for Ethernet.

        Hence, unless you have a good reason to do otherwise, it is
        recommended to use a transmit rate of 7812 Hz with a single 
        record per packet.
        '''
        #It is recommended to have a buffer size that is a multiple of 1024
        ceil_bytes = (1+int(self._data_size/1024))*1024
        data =  self._socket.recv(ceil_bytes)
        return data

    def _write(self, data: bytes) -> bool:
        '''
        Writes data to the socket. The data is sent to the IP address
        and port specified in the constructor.

        data: The data to send. Must be a bytes object.

        Returns True if all the data was sent, False otherwise.
        '''
        #Returns the number of bytes sent
        nbytes = self._socket.sendto(data, (self._ip_address, self._port))
        if nbytes != len(data):
            self._logger.warning("Sent {} bytes instead of {} bytes".format(nbytes, len(data)))
            return False
        return True

    def _rdt_request(self, command_code=0, sample_count=1):
        '''
        Sends a request to the Axia for starting or stopping the
        transmission of measurement data.

        Each request is built from:
        - 2 bytes: Header (0x1234)
        - 2 bytes: Command code. 0 = stop, 1 = start single-block, 3 = start multi-block
        - 4 bytes: Sample count (number of packets to transmit). 0 = infinite
        '''
        header = 0x1234
        command_code = command_code & 0xFFFF
        sample_count = sample_count & 0xFFFFFFFF
        data = header.to_bytes(2, 'big') + command_code.to_bytes(2, 'big') + sample_count.to_bytes(4, 'big')
        return data
    
    def stop_continuous_stream(self):
        '''
        Stops the transmission of measurement data.
        '''
        data = self._rdt_request(0, 0)
        self._write(data)

    def start_continuous_stream(self):
        '''
        Starts the transmission of measurement data in continuous mode.
        '''
        data = self._rdt_request(3, 0)
        self._write(data)
        logging.info("Started continuous stream at a rate of {} Hz".format(self._data_freq))

    def send_records(self, number_of_records=1):
        '''
        Sends a request to the Axia to transmit a given number of records.
        '''
        data = self._rdt_request(1, number_of_records)
        self._write(data)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    config = AxiaConfiguration()
    config.load_from_yaml('factory_configuration.yaml')
    udp = AxiaUdpListener(config)
    udp.connect()
    def cb(records):
        for rec in records:
            print('Fx: {}, Fy: {}, Fz: {}, Tx: {}, Ty: {}, Tz: {}'.format(rec['Fx'], rec['Fy'], rec['Fz'], rec['Tx'], rec['Ty'], rec['Tz']))
    udp.start_listening_thread(cb)
    udp.send_records(5)
    time.sleep(5)
    udp.stop_listening_thread()
    udp.disconnect()
        