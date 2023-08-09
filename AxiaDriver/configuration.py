import yaml
from pathlib import Path

'''
The AxiaConfiguration class is used to represent a specific configuration
of the Axia sensor, which can be loaded and saveed in YAML files.
'''


class AxiaConfiguration:
    '''
    Used to represent a specific configuration of the Axia sensor.
    '''
    def __init__(self) -> None:
        self._settings_dict = {}
    
    def load_from_yaml(self, yaml_file_path:str) -> None:
        '''
        Loads the configuration from a yaml file.
        '''
        yaml_file_path = Path(yaml_file_path)
        with open(yaml_file_path.resolve().as_posix(), 'r') as f:
            self._settings_dict = yaml.safe_load(f)
    
    def save_to_yaml(self, yaml_file_path:str) -> None:
        '''
        Saves the configuration to a yaml file.
        '''
        yaml_file_path = Path(yaml_file_path)
        with open(yaml_file_path.resolve().as_posix(), 'w') as f:
            yaml.dump(self._settings_dict, f)

    def _get_setting(self, setting_name:str) -> str:
        '''
        Returns the value of a specific setting.
        '''
        try:
            val = self._settings_dict[setting_name]
        except KeyError:
            val = None
        return val
    
    def _set_setting(self, setting_name:str, setting_value:str) -> None:
        '''
        Sets the value of a specific setting.
        '''
        self._settings_dict[setting_name] = setting_value

    @property
    def product_name(self) -> str:
        '''
        Returns the name of the product.
        '''
        return self._get_setting('productName')

    @property
    def current_config_serial_num(self) -> str:
        '''
        Returns the serial number of the active configuration.
        '''
        return self._get_setting('serialNum')
    
    @property
    def current_config_part_num(self) -> str:
        '''
        Returns the part number of the active configuration.
        '''
        return self._get_setting('partNum')
    
    @property
    def calibration_date(self) -> str:
        '''
        Returns the date on which the sensor was calibrated.
        '''
        return self._get_setting('calTime')
    
    @property
    def max_counts(self) -> str:
        '''
        Returns the maximum number of counts that the sensor can measure
        for each axis: Fx, Fy, Fz, Tx, Ty, Tz.

        This is influenced by the current calibration being used as the
        range of the sensor is different for each calibration.

        Returns a list of 6 integers: [max_counts_fx, max_counts_fy, max_counts_fz, max_counts_tx, max_counts_ty, max_counts_tz]
        '''
        max_counts_fx = self._get_setting('max0')
        max_counts_fy = self._get_setting('max1')
        max_counts_fz = self._get_setting('max2')
        max_counts_tx = self._get_setting('max3')
        max_counts_ty = self._get_setting('max4')
        max_counts_tz = self._get_setting('max5')
        return [max_counts_fx, max_counts_fy, max_counts_fz, max_counts_tx, max_counts_ty, max_counts_tz]
    
    @property
    def force_units(self) -> str:
        '''
        Returns the units of the force measurements as
        a string: 'lbf', 'N', 'kip', 'kN', 'Kg'. 

        Note: One kip is equal to 1000 lbf.
        '''
        unit_code = self._get_setting('forceUnits')
        if unit_code == '0':
            return 'lbf'
        elif unit_code == '1':
            return 'N'
        elif unit_code == '2':
            return 'kip'
        elif unit_code == '3':
            return 'kN'
        elif unit_code == '4':
            return 'kg'
        
    @property
    def torque_units(self) -> str:
        '''
        Returns the units of the torque measurements as
        a string: 'lbf-in', 'lbf-ft', 'N-m', 'N-mm', 'kg-cm', 'kN-m'. 
        '''
        unit_code = self._get_setting('torqueUnits')
        if unit_code == '0':
            return 'lbf-in'
        elif unit_code == '1':
            return 'lbf-ft'
        elif unit_code == '2':
            return 'N-m'
        elif unit_code == '3':
            return 'N-mm'
        elif unit_code == '4':
            return 'kg-cm'
        elif unit_code == '5':
            return 'kN-m'

    @property
    def units(self) -> str:
        '''
        Returns the units of the force and torque measurements as
        a strings.

        Force units: 'lbf', 'N', 'kip', 'kN', 'Kg'.
        Torque units: 'lbf-in', 'lbf-ft', 'N-m', 'N-mm', 'kg-cm', 'kN-m'.
        '''
        return self.force_units, self.torque_units

    @property
    def counts_per_force(self) -> str:
        '''
        Returns the number of counts per force unit.
        '''
        return self._get_setting('cpf')
    
    @property
    def counts_per_torque(self) -> str:
        '''
        Returns the number of counts per torque unit.
        '''
        return self._get_setting('cpt')
    
    @property
    def historical_peaks(self) -> str:
        '''
        Returns the maximal force and torque values that the sensor
        experiences along each axis, but positive and negative.

        This information is kept for the lifetime of the sensor and
        can be used to determine if the sensor has been overloaded
        in the past (not good).

        The values are expressed in counts.

        Returns a list of 6 tuples: [(max_fx, min_fx), (max_fy, min_fy), (max_fz, min_fz), (max_tx, min_tx), (max_ty, min_ty), (max_tz, min_tz)]
        '''
        max_fx = self._get_setting('peakPos0')
        min_fx = self._get_setting('peakNeg0')
        max_fy = self._get_setting('peakPos1')
        min_fy = self._get_setting('peakNeg1')
        max_fz = self._get_setting('peakPos2')
        min_fz = self._get_setting('peakNeg2')
        max_tx = self._get_setting('peakPos3')
        min_tx = self._get_setting('peakNeg3')
        max_ty = self._get_setting('peakPos4')
        min_ty = self._get_setting('peakNeg4')
        max_tz = self._get_setting('peakPos5')
        min_tz = self._get_setting('peakNeg5')

        return [(max_fx, min_fx), (max_fy, min_fy), (max_fz, min_fz), (max_tx, min_tx), (max_ty, min_ty), (max_tz, min_tz)]

    @property
    def firmware_version(self) -> str:
        '''
        Returns the firmware version of the sensor.
        '''
        return self._get_setting('firmware_version')
    
    @property
    def adc_rate(self) -> str:
        '''
        Returns the rate at which the sensor's ADC is sampling in Hz.

        Can be: 488, 976, 1953, 3906, 7812.
        '''
        return self._get_setting('adcRate')
    
    @property
    def udp_transmit_rate(self) -> str:
        '''
        Returns the rate at which the sensor is sending
        UDP packets in Hz. This value will be lower or equal
        to the ADC rate.
        '''
        return self._get_setting('rdtRate')
    
    @property
    def udp_records_per_packet(self) -> str:
        '''
        Returns the number of records that are sent in each
        UDP packet. This can be used to reduce the bandwith
        used by the data transmission.
        '''
        return self._get_setting('rdtSize')
    
    @property
    def filter_intensity(self) -> str:
        '''
        Returns the intensity of the low-pass filter applied
        to the data. The higher the value, the more filtering
        is applied and the greater the time delay.

        Can be: 0, 1, 2, 3, 4, 5, 6, 7, 8.
        '''
        return self._get_setting('filTc')
    
    @property
    def filter_cutoff_frequency(self) -> str:
        '''
        Returns the cutoff frequency of the low-pass filter
        applied to the data. This is the frequency at which
        the attenuation of the signal is 3 dB.

        The cutoff frequency is expressed in Hz and depends on
        the ADC rate and the filter intensity.
        '''
        adc_rate = self._get_setting('adcRate')
        adc_rate_index = {488: 0, 976: 1, 1953: 2, 3906: 3, 7812: 4}[adc_rate]
        filter_intensity = self._get_setting('filTc')

        cutoff_matrix = [
            [200,   350,    500,    1000, 2000],
            [58.4,  117,    234,    468,  935.10],
            [22.7,  45.5,   91,     182,  364.04],
            [10.6,  21.2,   42.4,   84.8, 169.52],
            [5.08,  10.2,   20.3,   40.6, 81.24],
            [2.49,  4.98,   9.96,   19.9, 39.84],
            [1.27,  2.54,   5.08,   10.2, 20.31],
            [0.586, 1.17,   2.34,   4.69, 9.37],
            [0.342, 0.683,  1.37,   2.73, 5.47]]
        
        return cutoff_matrix[filter_intensity][adc_rate_index]

    @property
    def calibration_number(self) -> str:
        '''
        Returns the active calibration number of the sensor.
        '''
        return self._get_setting('calib')
    
    @property
    def range(self) -> str:
        '''
        Returns the maximal forces and torques
        that the sensor can measure along each axis.

        Returns a dictionary with the following keys:
        - fx: Maximal force along the x axis
        - fy: Maximal force along the y axis
        - fz: Maximal force along the z axis
        - tx: Maximal torque about the x axis
        - ty: Maximal torque about the y axis
        - tz: Maximal torque about the z axis
        so you can access the values like this: range['fx'] 

        '''
        max_counts = self.max_counts
        cpf = self.counts_per_force
        cpt = self.counts_per_torque
        range_fx = max_counts[0] / cpf
        range_fy = max_counts[1] / cpf
        range_fz = max_counts[2] / cpf
        range_tx = max_counts[3] / cpt
        range_ty = max_counts[4] / cpt
        range_tz = max_counts[5] / cpt
        return {'fx': range_fx, 'fy': range_fy, 'fz': range_fz, 'tx': range_tx, 'ty': range_ty, 'tz': range_tz}
    
    @property
    def rated_accuracy(self) -> str:
        '''
        Returns the rated accuracy of the sensor
        for each axis.

        Note: The actual accuracy of the sensor can be
        lower or higher than the rated accuracy.

        Returns a dictionary with the following keys:
        - fx: Maximal force along the x axis
        - fy: Maximal force along the y axis
        - fz: Maximal force along the z axis
        - tx: Maximal torque about the x axis
        - ty: Maximal torque about the y axis
        - tz: Maximal torque about the z axis
        so you can access the values like this: rated_accuracy['fx'] 
        '''
        axes_range = self.range
        #Rated accuracy is 2% of the range
        rated_accuracy_fx = axes_range['fx'] * 0.02
        rated_accuracy_fy = axes_range['fy'] * 0.02
        rated_accuracy_fz = axes_range['fz'] * 0.02
        rated_accuracy_tx = axes_range['tx'] * 0.02
        rated_accuracy_ty = axes_range['ty'] * 0.02
        rated_accuracy_tz = axes_range['tz'] * 0.02
        return {'fx': rated_accuracy_fx, 'fy': rated_accuracy_fy, 'fz': rated_accuracy_fz, 'tx': rated_accuracy_tx, 'ty': rated_accuracy_ty, 'tz': rated_accuracy_tz}

    @property
    def is_good_status(self) -> bool:
        '''
        Returns True if the sensor is in a good status.
        '''
        return self._get_setting('good_status')
    
    @property
    def location(self) -> str:
        '''
        Returns the physical location of the sensor.
        '''
        return self._get_setting('location')
    
    @property
    def mac_address(self) -> str:
        '''
        Returns the MAC address of the sensor.
        '''
        return self._get_setting('mac')
    
    @property
    def ip_address(self) -> str:
        '''
        Returns the IP address of the sensor.
        '''
        return self._get_setting('sipadr')
    
    @property
    def has_static_ip(self) -> bool:
        '''
        Returns True if the sensor has a static IP address.
        '''
        return (self._get_setting('sipmode') == 1)
    
    @property
    def udp_port(self) -> str:
        '''
        Returns the UDP port used by the sensor.
        '''
        return self._get_setting('rdtPort')
    
    @property
    def biases(self):
        '''
        Returns the biases of the sensor as a list of 6 floats.
        Any bias that is not set will be returned as zero.

        The biases are expressed in the sensor's native units,
        (e.g. N or Nm), NOT IN COUNTS.
        '''
        bFx = self._get_setting('biasFx')
        if bFx is None:
            bFx = 0
        bFy = self._get_setting('biasFy')
        if bFy is None:
            bFy = 0
        bFz = self._get_setting('biasFz')
        if bFz is None:
            bFz = 0
        bTx = self._get_setting('biasTx')
        if bTx is None:
            bTx = 0
        bTy = self._get_setting('biasTy')
        if bTy is None:
            bTy = 0
        bTz = self._get_setting('biasTz')
        if bTz is None:
            bTz = 0

        return [bFx, bFy, bFz, bTx, bTy, bTz]
    
    def set_biases(self, biases):
        '''
        Record the supplied biases in the sensor configuration.
        WARNING: This only records the biases in the configuration
        file and does not write biases to the sensor memory even
        if the configuration is written to the sensor. This behaviour
        is intended as having multiple source of biases can be
        error prone.

        Parameters:
        biases: A list of 6 floats representing the biases to record
        in their respective units (e.g. N and Nm), NOT IN COUNTS.

        '''

        #Verify that the biases are floats
        for i in range(6):
            if type(biases[i]) != float:
                raise TypeError('Biases must be floats')

        self._set_setting('biasFx', biases[0])
        self._set_setting('biasFy', biases[1])
        self._set_setting('biasFz', biases[2])
        self._set_setting('biasTx', biases[3])
        self._set_setting('biasTy', biases[4])
        self._set_setting('biasTz', biases[5])