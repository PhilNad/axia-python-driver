import pickle
import logging
import time
import numpy as np
from pathlib import Path
from scipy.signal import savgol_filter
from configuration import AxiaConfiguration
from udp_listener import AxiaUdpListener
from unbiasing import Unbiasing
from ros_publisher import AxiaRosPublisher

'''
The data management module contains classes for recording, filtering, and saving
data received from the Axia sensor. A Recorder object can be used to record data
and save it to disk, with the possibility of filtering and/or unbiasing the data
before saving it. The Recorded can spawn a ROS publisher can be used to publish 
the data to the `AxiaWrench` ROS topic.

Note that the compute time involved in filtering and unbiasing the data is
significant and will reduce the rate at which data can be recorded. If possible
it is recommended to record the data without filtering or unbiasing, and then
perform these operations offline.
'''

class Recorder:
    '''
    Records data sent over UDP, and perform unbiasing, filtering, and
    saving to disk.
    '''
    def __init__(self, output_file_path:str, config:AxiaConfiguration, filter=None, unbiaser: Unbiasing = None,
                 UDP_listener:AxiaUdpListener = None, ros_publish:bool = False):
        '''
        output_file_path: Path to the output file where the data will be saved.
        config: An Axia Configuration object.
        UDP_listener: An AxiaUdpListener object. If None, then will be instantiated.
        '''

        #Verify that the output file can be written to
        output_file_path = Path(output_file_path)
        with open(output_file_path, 'ab') as f:
            f.close()

        #Configuration
        self._config = config
        if config is None:
            raise ValueError('AxiaConfiguration cannot be None.')
        
        #UDP Listener
        if UDP_listener is None:
            self._udp_listener = AxiaUdpListener(config)
        else:
            self._udp_listener = UDP_listener

        #Unbiasing
        if unbiaser is None:
            self._unbiaser = Unbiasing(config)
        else:
            self._unbiaser = unbiaser

        #Filtering
        self._filtering = filter

        #Saving
        self._saver = Saving(output_file_path, config, ros_publish)

        #The last sequence number received. The sequence starts at 0 when the sensor first
        # samples the ADCs, and increments by 1 for each sample. The sequence number is
        # rolled over to 0 when after it reaches (2**32 - 1).
        self._last_seq_number = None
        self._recording = False

        self._udp_listener.connect()
        self._udp_listener.start_listening_thread(self._callback)

    def __del__(self):
        self.stop_recording()
        self._udp_listener.disconnect()

    def start_recording(self):
        '''
        Start recording data.
        '''
        self._recording = True
        self._udp_listener.start_continuous_stream()

    def stop_recording(self):
        '''
        Stop recording data.
        '''
        self._recording = False
        self._udp_listener.stop_continuous_stream()
        self._udp_listener.stop_listening_thread()

    def _callback(self, records):
        '''
        Callback function for the UDP listener. This function is called
        when new data is received from the Axia sensor.

        records: A list of measurement records as described in _create_message().
        '''
        if self._recording:
            #Unbias
            unbiased_records = self._unbiaser.unbias(records)
            #Create numpy array
            rec_array = self.records_to_ndarray(unbiased_records)
            #Detect missed records
            self._detect_missed_records(rec_array)
            #Filter
            if self._filtering is not None:
                filtered_array = self._filtering.filter(rec_array)
            else:
                filtered_array = rec_array
            #Save
            self._saver.append(filtered_array)

    def _detect_missed_records(self, records_array:np.ndarray):
            '''
            Detect missed records in a numpy array of records.
            '''

            nb_missed_records = 0
            #Detect if there were missed records between the last
            # received record in the last batch and the first record
            # in the current batch.
            first_seq = records_array[0, 0]
            if self._last_seq_number is not None:
                if self._last_seq_number == 2**32 - 1:
                    expected_first_seq_number = 0
                else:
                    expected_first_seq_number = self._last_seq_number + 1
                #If seq number has rolled over, then the current seq will be less than the old seq.
                if first_seq < expected_first_seq_number:
                    nb_missed_records += 2**32 - expected_first_seq_number + first_seq
                #Otherwise, the current seq will be greater than the old seq.
                else:
                    nb_missed_records += first_seq - expected_first_seq_number
            #Detect if there were missed records between the records
            # in the current batch.
            seq_diff = np.diff(records_array[:, 0])
            missing_records = np.where(seq_diff > 1)[0]
            nb_missed_records += len(missing_records)
            #Output warning if there were missed records.
            if nb_missed_records > 0:
                logging.warning('Missed {} records'.format(nb_missed_records))
            #Update the last sequence number.
            self._last_seq_number = records_array[-1, 0]

            return nb_missed_records

    def records_to_ndarray(self, records):
        '''
        Returns the recorded data as a numpy ndarray.
        '''
        array = np.zeros((len(records), 7))
        for i, record in enumerate(records):
            seq = record['ft_sequence']
            fx = record['Fx']
            fy = record['Fy']
            fz = record['Fz']
            tx = record['Tx']
            ty = record['Ty']
            tz = record['Tz']
            array[i, :] = np.array([seq, fx, fy, fz, tx, ty, tz])
        return array


class Filtering:
    '''
    This class is used to filter the data from the Axia Driver while
    it is being collected.

    Filters:
    - Savitzky-Golay filter
    - Moving average filter
    - Exponential filter

    According to Mathworks:
        Savitzky-Golay smoothing filters are typically used to "smooth out" a noisy signal 
        whose frequency span (without noise) is large. They are also called digital smoothing 
        polynomial filters or least-squares smoothing filters. Savitzky-Golay filters perform 
        better in some applications than standard averaging FIR filters, which tend to filter 
        high-frequency content along with the noise. Savitzky-Golay filters are more effective 
        at preserving high frequency signal components but less successful at rejecting noise.
        Savitzky-Golay filters are optimal in the sense that they minimize the least-squares 
        error in fitting a polynomial to frames of noisy data.

    '''

    class Filter:
        def __init__(self, window_length:int = 5):
            self._window_length = window_length
            self._window_data = None
        
        def has_seq(self, data):
            # Is there a sequence number in the data?
            if data.shape[1] == 7:
                has_seq = 1
            else:
                has_seq = 0
            return has_seq

        def new_data(self, data:np.ndarray):
            '''
            Add new data to the window by overwriting the oldest data.
            If the window is uninitialized, then copies of the first
            data row are used to fill the window. (Nearest mode)
            '''
            #If the window has not yet been initialized
            if self._window_data is None:
                self._window_data = np.ndarray((self._window_length, data.shape[1]))
                #Fill the bottom of the window with the data chunk
                self._window_data[-data.shape[0]:, :] = data
                #Fill the top of the window with the first data row
                self._window_data[:self._window_length-data.shape[0], :] = data[0, :]
            else:
                #Move the window upward
                self._window_data = np.roll(self._window_data, -data.shape[0], axis=0)
                #Fill the bottom of the window with the data chunk
                self._window_data[-data.shape[0]:, :] = data

    class MovingAverageFilter(Filter):
        def __init__(self, window_length:int = 5):
            super().__init__(window_length)

        def filter(self, data:np.ndarray):
            '''
            Returns the filtered data.
            '''
            # Add new data to the window
            self.new_data(data)
            filtered_data = np.zeros(self._window_data.shape)
            has_seq = self.has_seq(data)
            if has_seq:
                #If there is a sequence number, simply copy it.
                filtered_data[:, 0] = self._window_data[:, 0]
            # Perform the filtering
            for i in range(6):
                filtered_data[:,has_seq+i] = np.convolve(self._window_data[:,has_seq+i], np.ones((self._window_length,)), mode='valid') / self._window_length
            # The size of the returned data should be the same as the input data.
            filtered_data = filtered_data[-data.shape[0]:, :]
            return filtered_data
        
    class ExponentialFilter(Filter):
        def __init__(self, window_length:int = 5, alpha:float = 0.5):
            super().__init__(window_length)
            self._alpha = alpha

        def filter(self, data:np.ndarray):
            '''
            Returns the filtered data.
            '''
            # Add new data to the window
            self.new_data(data)
            filtered_data = np.zeros(self._window_data.shape)
            has_seq = self.has_seq(data)
            if has_seq:
                #If there is a sequence number, simply copy it.
                filtered_data[:, 0] = self._window_data[:, 0]
            # Perform the filtering
            for i in range(1, len(self._window_data)):
                filtered_data[i,has_seq:] = self._alpha * self._window_data[i,has_seq:] + (1 - self._alpha) * filtered_data[i-1,has_seq:]
            # The size of the returned data should be the same as the input data.
            filtered_data = filtered_data[-data.shape[0]:, :]
            return filtered_data

    class SavitzkyGolayFilter(Filter):
        def __init__(self, window_length:int = 11, order:int = 3):
            super().__init__(window_length)
            self._order = order

        def filter(self, data:np.ndarray):
            '''
            Returns the filtered data.
            '''
            # Add new data to the window
            self.new_data(data)
            # Perform the filtering
            return savgol_filter(self._window_data, self._window_length, self._order, axis=0, mode='mirror')


class Saving:
    '''
    This class is used to save recorded data to disk.
    '''
    def __init__(self, file_path:str, config:AxiaConfiguration=None, ros_publish:bool = False):
        '''
        file_path: The name of the file to save data to.
        ros_publish: If True, then publish the data to ROS. Requires a valid AxiaConfiguration.
        '''
        self._file_path = Path(file_path).resolve()
        self._filedescriptor = None
        self._ros_publisher = None

        #The data is stored in a numpy array with the following columns:
        # - ft_sequence: The sequence number of the measurement record.
        # - Fx: The force in the x-direction.
        # - Fy: The force in the y-direction.
        # - Fz: The force in the z-direction.
        # - Tx: The torque about the x-axis.
        # - Ty: The torque about the y-axis.
        # - Tz: The torque about the z-axis.
        self._data = np.ndarray((0, 7))

        #If the extension is .csv, then save to CSV. Otherwise, save to pickle.
        if self._file_path.suffix == '.csv' or self._file_path.suffix == '.CSV':
            self.open   = self._open_csv
            self.append = self._append_to_csv
        else:
            self.open   = self._open_pickle
            self.append = self._append_to_pickle

        self._filedescriptor = self.open()

        if ros_publish and config is not None:
            self._ros_publisher = AxiaRosPublisher(config)

    def __del__(self):
        #Close the file on destruction.
        self.close()

    def _open_pickle(self):
        '''
        Open the pickle file for appending.
        '''
        fd = open(self._file_path, 'ab')
        #Verify that the file could be opened.
        if fd is None:
            raise IOError("Could not open file {}".format(self._file_path))
        self._filedescriptor = fd
        return fd

    def _open_csv(self):
        '''
        Open the CSV file for appending.
        '''

        fd = open(self._file_path, 'a')
        #Verify that the file could be opened.
        if fd is None:
            raise IOError("Could not open file {}".format(self._file_path))
        self._filedescriptor = fd
        return fd

    def _append_to_pickle(self, records):
        '''
        Append a record to the pickle file.

        # A record is a dictionary with the following keys:
        #     - rdt_sequence
        #     - ft_sequence
        #     - status
        #     - Fx
        #     - Fy
        #     - Fz
        #     - Tx
        #     - Ty
        #     - Tz

        '''
        for record in records:
            pickle.dump(record, self._filedescriptor)
        if self._ros_publisher is not None:
            self._ros_publisher._callback(records)

    def _append_to_csv(self, records):
        '''
        Append a record to the CSV file.
        '''
        for record in records:
            if type(record) is np.ndarray:
                self._filedescriptor.write("{},{},{},{},{},{},{}\n".format(
                    record[0],
                    record[1],
                    record[2],
                    record[3],
                    record[4],
                    record[5],
                    record[6]))
            if type(record) is dict:
                self._filedescriptor.write("{},{},{},{},{},{},{}\n".format(
                    record['ft_sequence'],
                    record['Fx'],
                    record['Fy'],
                    record['Fz'],
                    record['Tx'],
                    record['Ty'],
                    record['Tz']))
        if self._ros_publisher is not None:
            self._ros_publisher._callback(records)
        
    def close(self):
        '''
        Close the file.
        '''
        self._filedescriptor.close()

if __name__ == '__main__':
    config = AxiaConfiguration()
    config.load_from_yaml('Axia_Joe_Config.yaml')
    filter = Filtering.MovingAverageFilter(window_length=8)
    recorder = Recorder('debias.csv', config, filter=filter, ros_publish=False)
    recorder.start_recording()
    time.sleep(10)
    recorder.stop_recording()
