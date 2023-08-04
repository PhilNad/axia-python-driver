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

    async def read_buffer(self, pattern_to_find=b'\n', timeout=5):
        '''
        Reads until the specified pattern is found in the buffer
        or until the timeout (seconds) is reached.

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
            data = await self.reader.read(1)
            if not data:
                #Received EOF
                break
            buffer += data
            #If the byte received is the last byte in the pattern, check if the pattern is found in the buffer
            if data == pattern_to_find[-1]:
                if re.search(pattern_to_find, buffer) is not None:
                    break
            #If the timeout is reached, break
            if time.time() - start_time > timeout:
                timed_out = True
                break
        return timed_out, buffer

    def read_all(self, max_bytes=2**16):
        '''
        Reads any number of bytes until EOF is received.
        This can potentially be blocking if the server does not send EOF.
        '''
        loop = asyncio.get_event_loop()
        data = loop.run_until_complete(self.reader.read(max_bytes))
        return data
    
    def read_until(self, pattern=b'\n', timeout=5):
        '''
        Reads until the specified byte is received.
        '''
        loop = asyncio.get_event_loop()
        timed_out, data = loop.run_until_complete(self.read_buffer(pattern, timeout))
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
        data = self.read_all()
        lines_with_pattern = self.find_lines_with_pattern(data, pattern)
        return lines_with_pattern

    def write(self, data):
        '''
        Writes data to the sensor and appends a newline character.
        '''
        self.writer.write(str(data) + "\n")

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

        lines = self.read_and_match_pattern('Password:')
        if len(lines) == 0:
            raise Exception('Password prompt not found')
        self.write(password)
        
        lines = self.read_and_match_pattern('Logged in successfully')
        if len(lines) == 0:
            raise Exception('Login failed. Incorrect username or password.')

        timed_out, data = self.read_until('>')
        if timed_out:
            raise Exception('No prompt found after login.')
        
        logging.info('Logged in successfully.')
        

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sensor_ip = '192.168.1.1'
    com = Communication(sensor_ip)
    com.connect()
    com.disconnect()
