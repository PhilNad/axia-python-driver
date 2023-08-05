import asyncio
import telnetlib3
import re
import logging
import time

class Communication:
    def __init__(self, ip_address) -> None:
        self.sensor_ip = ip_address
        self.sensor_port = 23
        self.connected = False
    
    def connect(self, username='ati', password='ati7720115'):
        loop = asyncio.get_event_loop()
        self.reader, self.writer = loop.run_until_complete(telnetlib3.open_connection(self.sensor_ip, self.sensor_port))
        self.login(username, password)
        self.connected = True

    def disconnect(self):
        if self.connected:
            self.reader.close()
            self.writer.close()
            self.connected = False

    async def read_buffer(self, pattern_to_find='\r\n', timeout=5):
        '''
        Reads until the specified pattern is found in the buffer
        or until the timeout (seconds) is reached. Hence, the data
        returned will not contain the pattern if it is found.

        pattern_to_find: Regex pattern to find in the buffer.
        timeout: Timeout in seconds.

        Returns a tuple (timed_out, buffer)
        timed_out is True if the timeout is reached.
        buffer is the data read until the timeout or pattern is found.
        '''
        buffer = ''
        start_time = time.time()
        timed_out = False
        while True:
            try:
                data = await asyncio.wait_for(self.reader.read(1), timeout=timeout)
                buffer += data
            except asyncio.exceptions.TimeoutError:
                timed_out = True
                break

            if not data:
                #Received EOF
                break

            #If the byte received is the last byte in the pattern, check if the pattern is found in the buffer
            if data == pattern_to_find[-1]:
                match = re.search(pattern_to_find, buffer)
                if  match is not None:
                    #Return the data without the pattern
                    buffer = buffer[:match.start()]
                    break
            #If the timeout is reached, break
            if time.time() - start_time > timeout:
                timed_out = True
                break
        return timed_out, buffer
    
    def read_until(self, pattern='\r\n', timeout=5):
        '''
        Reads until the specified pattern is received.
        '''
        loop = asyncio.get_event_loop()
        timed_out, data = loop.run_until_complete(self.read_buffer(pattern, timeout))
        if timed_out:
            logging.warning('Timeout reached while waiting for pattern: ' + str(pattern))
        return timed_out, data

    def find_lines_with_pattern(self, data, pattern):
        '''
        Assuming that data contains a number of lines, this function will
        return a list of lines containing the pattern.
        '''
        lines = data.splitlines()
        lines_with_pattern = []
        for line in lines:
            if re.search(pattern, line) is not None:
                lines_with_pattern.append(line)
        return lines_with_pattern

    def read_and_match_pattern(self, pattern):
        '''
        Reads all data and returns a list of lines containing the pattern.
        '''
        _, data = self.read_until('\r\n>')
        lines_with_pattern = self.find_lines_with_pattern(data, pattern)
        return lines_with_pattern

    def write(self, data):
        '''
        Writes data to the sensor and appends a newline character.
        '''
        self.writer.write(str(data) + "\r\n")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.writer.drain())

    def login(self, username, password):
        '''
        Logs in to the sensor using the specified username and password.

        Upon connection, the prompt will be:
            Telnet Server 1.1
            Login: ati
            Password: ati7720115

            Logged in successfully


            --- Telnet Console ---
            Type help for commands
            >
        '''
        timed_out, data = self.read_until('Login: ')
        if timed_out:
            raise Exception('Login prompt not found')
        self.write(username)

        timed_out, data = self.read_until('Password: ')
        if timed_out:
            raise Exception('Password prompt not found')
        self.write(password)
        
        timed_out, data = self.read_until('Logged in successfully')
        if timed_out:
            raise Exception('Login failed. Incorrect username or password.')

        timed_out, data = self.read_until('>')
        if timed_out:
            raise Exception('No prompt found after login.')
        
        logging.info('Logged in successfully.')

    def get_system_version(self):
        '''
        Get the firmware version of the sensor.

        >sysver
        sysver
        1.0.29 => Aug 27 2019 10:25:24 BL=4
        >
        '''
        if not self.connected:
            raise Exception('Not connected to sensor.')
        self.write('sysver')
        _, data = self.read_until('\r\n>')
        lines = data.split('\r\n')
        version = lines[1].split(' ')[0]
        return version
    
    def disable_bias(self):
        '''
        It is very error prone to set a bias directly in the sensor
        as users might also set biases elsewhere. Hence, the bias
        function should always be disabled.

        >bias off
        bias off
        BIAS OFF
        >

        '''
        self.write('bias off')
        _, data = self.read_until('\r\n>')
        if 'BIAS OFF' not in data:
            raise Exception('Could not disable bias.')
        else:
            logging.info('Bias disabled.')

    def set_setting(self, name, value):
        '''
        Sets a setting to the specified value.
        '''
        self.write('set ' + name + ' ' + str(value))
        _, data = self.read_until('\r\n>')
        if 'not changed' in data:
            old_value = new_value = value
        else:
            pattern = '{} was "(\d+)" now "(\d+)"'.format(name)
            match = re.search(pattern, data)
            if match is not None:
                old_value = int(match.group(1))
                new_value = int(match.group(2))
            else:
                logging.warning('Could not parse response: ' + data)
        logging.info('{} set to {}'.format(name, new_value))
        return old_value, new_value

    def set_adc_sample_rate(self, rate=7812):
        '''
        Sets the ADC sample rate in Hz. The rate must be one
        of the following: 488, 976, 1953, 3906, 7812
        '''
        if rate not in [488, 976, 1953, 3906, 7812]:
            raise Exception('Invalid sample rate. Must be one of 488, 976, 1953, 3906, 7812')
        old_rate, new_rate = self.set_setting('adcrate', rate)
        return old_rate, new_rate

    def set_udp_transmit_rate(self, rate=488):
        '''
        Set the rate at which the sensor will send UDP packets.
        By default, each packet contains a single sample (this can be changed
        with the rdtSize setting but we choose not to). A valid rate is between
        1 and the current ADC rate. Trying to set an invalid rate will not
        result in any actual change. However, the output from the sensor
        will indicate that the rate has been changed.

        At the maximal rate of 7812 Hz, the UDP stream will consume 
        7812*288 = 4.3 Mbps of bandwidth, and storing the FT data will
        produce 6*4*7812 = 183 kB/s of data or 10.7 MB/min.

        Each UDP packet contains 9*32 = 36 bytes = 288 bits of data:
        - Uint32 rdt_sequence
        - Uint32 ft_sequence
        - Uint32 status
        - Int32 Fx
        - Int32 Fy
        - Int32 Fz
        - Int32 Tx
        - Int32 Ty
        - Int32 Tz
        Each UDP packet also contains 36 bytes of header information.

        For debugging UDP on Linux, the following command can be sent to
        start continuously transmitting UDP packets:
            echo -e '\x12\x34\x00\x03\x00\x00\x00\x00' | nc -4u -w1 192.168.1.1 49152 > /dev/null &
        and the transmisstion can be stopped with:
            echo -e '\x12\x34\x00\x00\x00\x00\x00\x00' | nc -4u -w1 192.168.1.1 49152

        For instance:
            >set rdtrate -2
            set rdtrate -2
            rdtrate not changed
            >set rdtrate 1500
            set rdtrate 1500
            rdtrate was "976" now "1500"
            >set rdtrate
            set rdtrate

            Field        Value
            -----        -----
            rdtRate      976
            >
        '''
        old_rate, new_rate = self.set_setting('rdtrate', rate)
        return old_rate, new_rate

    def set_low_pass_filter(self, filter_intensity=0):
        '''
        Sets the time constant of the low-pass filter. The filter intensity must be
        between 0 and 8. When the filter intensity is 0, the filter is
        disabled. Choosing to use a filter does not change the data
        rate. However, for a higer data rate, the cutoff frequency
        of the filter will be lower.

        A greater filter intensity will presumably introduce a greater delay.
        See the user manual to know the cutoff frequency for each filter.
        '''
        if filter_intensity not in range(9):
            raise Exception('Invalid filter intensity. Must be between 0 and 8.')
        old_intensity, new_intensity = self.set_setting('filtc', filter_intensity)
        return old_intensity, new_intensity

    def set_calibration(self, calibration_id):
        '''
        Sets the calibration to use. The calibration ID must be
        one that is available on the sensor. For the Axia, two
        calibrations are available: 0 and 1.
        '''
        if calibration_id not in range(2):
            raise Exception('Invalid calibration ID. Must be 0 or 1.')
        old_id, new_id = self.set_setting('calib', calibration_id)
        return old_id, new_id
    
    def set_location(self, location_description):
        '''
        Set a location string that describes where is the sensor.

        The maximal length of the string is 40 characters.
        '''
        if len(location_description) > 40:
            raise Exception('Location description must be less than 40 characters.')
        old_description, new_description = self.set_setting('location', location_description)
        return old_description, new_description

    def get_status(self):
        '''
        Get the status of the sensor. If no component is stating
        that its status is "BAD", then the sensor is considered
        to be in good health and the status is True. Otherwise,
        the status is False, and a list of lines in which the
        status is "BAD" is returned.

        Example output:
            >status
            status
            NVM-Image-0 Good  551 Kbytes 
            NVM-Image-1 ---- 
            SPI-Param-0 Good 1436  bytes
            SPI-Param-1 Good 1436  bytes
            RAM-Param   Good 1436  bytes
            MCU-RAM     ----  512 Kbytes Errors: 0
            Stack       Good  383 Kbytes available
            UART1       ---- 115.4 KHz RX faults: 0
            REFCLKO     ----   4.0 MHz
            SPI2-ADC    ----  14.0 MHz
            SPI4-EEPROM ----   8.4 MHz
            MCU-Clock   Good 168.0 MHz
            ISR-ADC     Good 976.6  Hz  38.0 usec Max:  57.1 usec Overruns: 0
            ISR-PHY     Good  23.9  Hz   0.3 usec Max:   2.1 usec Overruns: 0
            Background  ---- 103.3 KHz   9.5 usec Max:  45.8 msec Overruns: 0
            MCU-Part    Good PIC32MZ2048EFH064 A6 S/N: 7e65cc22 e762a064
            MCU-FPU     ---- ID=a7 REV=32 UFRP=1 FC=1 HAS08=1 F64=1 L=1 W=1 3D=0 PS=0 D=1 S=1 FS=1 FO=0 FN=0 MAC=0 ABS=1 NAN=1 RM=0
            MCU-WatchDg Good   2.0  sec Windowed: Off
            MCU-RCON    Good BrownOutReset PowerOnReset
            MCU-Regs    Good 
            MCU-PC      Good 
            MCU-GPIO    Good 
            MCU-Supply  Good  24.0 V
            PCB-Temp    Good  38.2 *C
            Gage-Temp   Good  22.9 *C
            ADC-Gages   Good Spikes: 0 
            ADC-RegWr   Good Resets: 1
            SPI-EEPROM  Good Type: 24-bit Tries: 1
            Host        Good Name: AXIAETHERNET    IP: 192.168.1.1 Gateway: 0.0.0.0 MAC: 00:16:bd:00:42:57 Up Linked Ready
            rdtPort     ---- 49152
            tcpPort     ---- 49151
            telnetPort  ----    23
            >
        '''
        self.write('status')
        lines = self.read_and_match_pattern('BAD')
        good_status = (len(lines) == 0)
        return good_status, lines
        

    def write_settings_to_memory(self):
        '''
        Writes the current configuration to the non-volatile memory.

        Example output:
            >saveall
            saveall
            Parameters saved to NVM bank 0
            Parameters saved to NVM bank 1
            >
        '''
        self.write('saveall')
        _, data = self.read_until('\r\n>')
        if 'Parameters saved to NVM bank 0' not in data:
            raise Exception('Could not write settings to memory.')
        else:
            logging.info('Settings written to memory.')

    def get_settings(self):
        '''
        Gets the current settings of the sensor.

        Example output:
        >set
        set

        Field        Value
        -----        -----
        serialNum    FT45616
        partNum      SI-150-8
        calFamily    ENET
        calTime      4/27/2023
        max0         111369318
        max1         111369318
        max2         493500000
        max3         5939697
        max4         5939697
        max5         8400000
        forceUnits   1
        torqueUnits  2
        cpf          1000000
        cpt          1000000
        peakPos0     225000000
        peakPos1     225000000
        peakPos2     705000000
        peakPos3     12000000
        peakPos4     12000000
        peakPos5     12000000
        peakNeg0     -225000000
        peakNeg1     -225000000
        peakNeg2     -705000000
        peakNeg3     -12000000
        peakNeg4     -12000000
        peakNeg5     -12000000
        sensorHwVer  0
        sensorInstr  0
        paramWrites  0
        adcRate      976
        rdtRate      976
        rdtSize      1
        rdtPort      49152
        tcpPort      49151
        telnetPort   23
        filTc        0
        calib        0
        location     Insert your location here
        serNum       Serial number
        hwProdCode   HW Product Code
        hwRev        0
        sipmode      1
        sipadr       192.168.1.1
        sipmsk       255.255.255.0
        sipgtw       0.0.0.0
        mac          00:16:bd:00:42:57
        sf0          4578
        sf1          4578
        sf2          14344
        sf3          245
        sf4          245
        sf5          245
        ttdu         4
        ttau         1
        ttdx         0
        ttdy         0
        ttdz         0
        ttrx         0
        ttry         0
        ttrz         0
        baud         115200
        msg          0
        serial       0
        productName  ATI Axia F/T Sensor
        holdTime     32
        mcEnabled    0
        mcOutMomen   0
        mcOutDelay   0
        mcAndCodes   0
        '''
        if not self.connected:
            raise Exception('Not connected to sensor.')
        self.write('set')
        timeout,_ = self.read_until('-----\r\n', timeout=5)
        if timeout:
            raise Exception('Timeout while waiting for settings.')
        _, data = self.read_until('\r\n>')
        #Each line is separated by \r\n
        lines = data.split('\r\n')
        data_dict = {}
        for line in lines:
            #The first space separates the field and value
            field, value = line.split(' ', 1)
            #Strip any leading spaces from the value
            value = value.strip()
            #If the value is a number, convert it to an int
            if value.isdigit():
                value = int(value)
            #Add the field and value to the dictionary
            data_dict[field] = value
        return data_dict
        
        

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    sensor_ip = '192.168.1.1'
    com = Communication(sensor_ip)
    com.connect()
    settings = com.get_settings()
    com.disable_bias()
    print(com.get_system_version())
    print(com.get_status())
    #com.set_adc_sample_rate(7812)
    #com.set_udp_transmit_rate(7812)
    #com.set_low_pass_filter(8)
    #com.set_calibration(1)
    #com.set_location('Joe')
    com.disconnect()
