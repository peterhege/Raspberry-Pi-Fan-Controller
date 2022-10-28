#!/usr/bin/env python3
# coding: utf-8
import json
import os

try:
    import typing
except:
    pass

FAN_PIN = 21  # BCM pin used to drive transistor's base
WAIT_TIME = 1  # [s] Time to wait between each refresh
FAN_MIN = 40  # [%] Fan minimum speed.
PWM_FREQ = 25  # [Hz] Change this value if fan has strange behavior
NIGHT_FROM = 22
NIGHT_TO = 7
FAN_DATA = os.path.dirname(os.path.realpath(__file__)) + '/fan_speed.json'


class Config:
    ROOT = 'data'
    config = None  # type: typing.Union[ConfigType, Config, None]

    config_data = {}
    modifier_data = {}

    config_modified = False
    modifier_modified = False

    @staticmethod
    def menu():
        instance = Config.instance()
        menu = [
            {'name': 'Calibrate Frequency', 'method': instance.calibrate_frequency}
        ]
        print('What would you like to do?\n')
        for i in range(len(menu)):
            print('{i}. {name}'.format(i=i, name=menu[i]['name']))

        menu_index = input('Menu Index: ')
        if not menu_index.isnumeric():
            print('Error: Invalid index!\n')
            Config.menu()

        menu_index = int(menu_index)
        if menu_index < 0 or menu_index >= len(menu):
            print('Error: Invalid index!\n')
            Config.menu()

        menu[menu_index]['method']()

    @staticmethod
    def instance(force_config=False, force_modifier=False):  # type: (bool, bool) -> typing.Union[Config, ConfigType]
        force_config = Config.config is None or force_config
        force_modifier = Config.config is None or force_modifier

        if force_config or force_modifier:
            Config.init(force_config, force_modifier)

        return Config.config

    @staticmethod
    def init(read_config=False, read_modifier=False):
        if Config.config is None:
            Config.config = Config()
        if read_config:
            Config.read('config')
        if read_modifier:
            Config.read('modifier')

    @staticmethod
    def read(filename):
        for k, v in IO.read(Config.filename(filename)).items():
            setattr(Config.config, k, v)

    @staticmethod
    def filename(filename):
        return '{root}/{file}.json'.format(root=Config.ROOT, file=filename)

    def __setattr__(self, key, value):
        if key in ['freq']:
            self.config_modified = True
            self.config_data[key] = value
        if key in ['']:
            self.modifier_modified = True
            self.modifier_data[key] = value

    def __getattr__(self, item):
        if item in self.config_data:
            return self.config_data[item]
        if item in self.modifier_data:
            return self.modifier_data[item]
        return None

    def calibrate_frequency(self):
        pass


class ConfigType:
    freq = None  # type: int


class IO:
    ROOT = os.path.dirname(os.path.realpath(__file__))

    @staticmethod
    def read(filename):  # type: (str) -> dict
        if not os.path.exists(filename):
            IO.write(filename, {})
        with open(IO.filename(filename), 'r') as f:
            return json.load(f)

    @staticmethod
    def write(filename, dictionary):  # type: (str,dict) -> None
        with open(IO.filename(filename), 'w') as f:
            json.dump(dictionary, f)

    @staticmethod
    def filename(filename):  # type: (str) -> str
        return '{root}/{file}'.format(root=IO.ROOT, file=filename)
