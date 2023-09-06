import csv
from pathlib import Path

import numpy as np

class Unbiasing:
    '''
    This class is used to unbias the data from the Axia Driver from
    the biases that are either supplied at initialization or loaded
    from an Axia Configuration.
    '''
    def __init__(self, config=None):
        '''
        config: An Axia Configuration object. If None, then the biases
        are assumed to be zero.
        '''
        self._config = config
        if config is None:
            self._biases = np.zeros(6)
        else:
            self._biases = self.set_config(config)
    
    def set_biases(self, bias):
        '''
        bias: A 6-element numpy array containing the biases to use.
        '''
        self._biases = bias

    def set_config(self, config):
        '''
        config: An Axia Configuration object.
        '''
        self._config = config
        self._biases = np.array(self._config.biases)

        return self._biases
    
    def average_from_csv(self, file_path:str):
        """
        Computes biases by averaging record data from a csv file.
        Arguments:
        :param str file_path: CSV file to read data and average biases from.
        """
        data_list = []
        file_path = Path(file_path).resolve()

        assert file_path.suffix.lower() == '.csv', "File must be csv"

        with open(file_path, "r") as f:
            reader = csv.reader(f)
            for line in reader:
                data_list.append(list(map(float, line[1:])))
        data_array = np.array(data_list)
        bias = np.average(data_array, axis=0)

        self.set_biases(bias)

    def unbias(self, records):
        '''
        Unbias a list of measurement record.

        Each record is a dictionary with the following keys:
        - rdt_sequence
        - ft_sequence
        - status
        - Fx
        - Fy
        - Fz
        - Tx
        - Ty
        - Tz

        The biases are subtracted from the data.
        '''

        for record in records:
            record['Fx'] -= self._biases[0]
            record['Fy'] -= self._biases[1]
            record['Fz'] -= self._biases[2]
            record['Tx'] -= self._biases[3]
            record['Ty'] -= self._biases[4]
            record['Tz'] -= self._biases[5]
        return records
    
    def unbias_single(self, record):
        '''
        Unbias a single measurement record.

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

        The biases are subtracted from the data.
        '''
        record['Fx'] -= self._biases[0]
        record['Fy'] -= self._biases[1]
        record['Fz'] -= self._biases[2]
        record['Tx'] -= self._biases[3]
        record['Ty'] -= self._biases[4]
        record['Tz'] -= self._biases[5]
        return record
