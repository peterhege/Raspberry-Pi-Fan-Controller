#!/usr/bin/env python3
# coding: utf-8

import json
import math
import os
import datetime
import time
import typing

try:
    import RPi.GPIO as GPIO
except (RuntimeError, ModuleNotFoundError):
    from fake_rpi.RPi import GPIO

FAN_PIN = 21  # BCM pin used to drive transistor's base
WAIT_TIME = 1  # [s] Time to wait between each refresh
FAN_MIN = 40  # [%] Fan minimum speed.
PWM_FREQ = 25  # [Hz] Change this value if fan has strange behavior


class Controller:
    pwm = None  # type: GPIO.PWM
    pin = None  # type: int

    @staticmethod
    def fan():
        pin = Config.pin()

        if Controller.pwm is None or pin != Controller.pin:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(FAN_PIN, GPIO.OUT, initial=GPIO.LOW)

            Controller.pin = pin
            Controller.pwm = GPIO.PWM(pin, Config.freq())
            Controller.pwm.start(0)

        return Controller.pwm

    @staticmethod
    def speed(speed, min_speed=None):
        if min_speed is None:
            min_speed = Config.min()

        if speed > 100:
            speed = 100
        if speed < min_speed:
            speed = min_speed

        Controller.fan().ChangeDutyCycle(speed)

    @staticmethod
    def freq(freq):
        if freq < 1:
            freq = 1
        Controller.fan().ChangeFrequency(freq)


class Config:
    ROOT = 'fan_ctrl_data'
    config = None  # type: typing.Union[ConfigType, ConfigData, None]

    @staticmethod
    def menu():
        instance = Config.instance()

        if instance.pin is None:
            return instance.install()

        if instance.min is None:
            instance.calibrate_min_speed()

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
        Config.menu()

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
            Config.config = ConfigData()
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

    @staticmethod
    def pin():
        instance = Config.instance()
        if instance.pin:
            return instance.pin
        return FAN_PIN

    @staticmethod
    def freq():
        instance = Config.instance()
        if instance.freq:
            return instance.freq
        return PWM_FREQ

    @staticmethod
    def min():
        instance = Config.instance()
        if instance.min:
            return instance.min
        return FAN_MIN


class ConfigData:
    config_data = {}
    modifier_data = {}

    config_modified = False
    modifier_modified = False

    def __setattr__(self, key, value):
        if key in ['freq', 'min', 'pin']:
            self.config_modified = True
            self.config_data[key] = value
        else:
            if key in ['periods']:
                value = ModificationPeriods(value)
            self.modifier_modified = True
            self.modifier_data[key] = value

    def __getattr__(self, item):
        if item in self.config_data:
            return self.config_data[item]
        if item in self.modifier_data:
            return self.modifier_data[item]
        return None

    def install(self):
        self.set_pin()

        Controller.speed(100)

        works = input('Is the fan working properly? [Y/n]').lower() == 'y'
        if not works:
            self.calibrate_frequency()

        self.calibrate_min_speed()

    def set_pin(self):
        pin = input('Fan GPIO Pin: ')
        pins = list(range(2, 13 + 1)) + list(range(16, 27 + 1))
        if not pin.isnumeric() or int(pin) not in pins:
            print('Invalid GPIO Pin: {}! Valid pins: {}'.format(pin, ', '.join(pins)))
            return self.set_pin()

        self.pin = int(pin)

    def calibrate_min_speed(self):
        print('Increase the value until the fan moves. When it moves, write done.')
        # TODO

    def calibrate_frequency(self):
        Controller.speed(100)
        print('Change the value until the fan working properly. When it fine, write done.')
        valid = False

        while True:
            freq = input('Frequency value: ')
            if freq.lower() == 'done':
                break
            if not freq.isnumeric() or int(freq) < 1:
                print('Invalid Frequency value: {}'.format(freq))
                valid = False
                continue
            valid = True
            Controller.freq(int(freq))

        if valid:
            self.freq = int(freq)


class ConfigType:
    """ PWM Frequency [Hz] """
    freq = None  # type: int
    """ Fan min speed [%] """
    min = None  # type: int
    """ BCM pin used to drive transistor's base """
    pin = None  # type: int
    """ Modification period, for example, slower at night """
    periods = None  # type: ModificationPeriods


class ModificationPeriods:
    list = []  # type: typing.List[ModificationPeriod]
    active = None  # type: int
    next = None  # type: int

    def __init__(self, periods):
        def comp(a, b):  # type: (ModificationPeriod,ModificationPeriod) -> float
            return a.start - b.start

        self.list = [ModificationPeriod(**period) for period in periods]
        self.list.sort(key=comp)

        now = ModificationPeriod.seconds(datetime.datetime.now())
        i = 0
        for i in range(len(self.list)):
            if now >= self.list[i].start:
                break
        self.active = i
        self.next = i + 1 if i < len(self.list) else 0

    def get(self):
        if not self.list:
            return None
        time_now = ModificationPeriod.seconds(datetime.datetime.now())
        while not (
                (
                        self.list[self.active].start < self.list[self.next].start and
                        self.list[self.active].start <= time_now < self.list[self.next].start
                ) or (
                        self.list[self.active].start >= self.list[self.next].start and
                        not (self.list[self.active].start >= time_now > self.list[self.next].start)
                )
        ):
            self.active = self.next
            self.next = self.active + 1 if self.active < len(self.list) else 0
        return self.list[self.active]


class ModificationPeriod:
    """ Start of period in seconds """
    start = None  # type: float
    """ Current fan speed modifier [%] """
    modifier = None  # type: SpeedModifier

    def __init__(
            self,
            start,  # type: typing.Union[str,float,datetime.datetime,time.struct_time]
            modifier  # type: typing.Union[str,int,float,dict,SpeedModifier]
    ):
        self.start = ModificationPeriod.seconds(start)
        self.modifier = modifier if type(modifier) is SpeedModifier else SpeedModifier.create(modifier)

    def modify(self, speed, temp):  # type: (float,float) -> float
        return self.modifier.modify(speed, temp)

    @staticmethod
    def seconds(t):  # type: (typing.Union[str,float,datetime.datetime,time.struct_time]) -> float
        """ str,float,datetime.datetime,time.struct_time """
        tt = type(t)
        if tt is float or tt is int:
            return t

        if tt is str:
            if t.isnumeric():
                return float(t)
            t = datetime.datetime.strptime(t, '%H:%M:%S')
            tt = type(t)

        if tt is datetime.datetime:
            delta = datetime.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        else:
            delta = datetime.timedelta(hours=t.tm_hour, minutes=t.tm_min, seconds=t.tm_sec)

        return delta.total_seconds()


class SpeedModifier:
    @staticmethod
    def create(modifier):
        if type(modifier) is dict:
            return TempSpeedModifier(**modifier)
        else:
            return SimpleSpeedModifier(modifier)

    def modify(self, speed, temp):  # type: (float, float) -> float
        return self.calculate(speed, temp)

    def calculate(self, speed, temp):  # type: (float, float) -> float
        return speed


class SimpleSpeedModifier(SpeedModifier):
    modifier = None  # type: float

    def __init__(self, modifier):
        self.modifier = modifier

    def calculate(self, speed, temp=None):  # type: (float, float) -> float
        return speed + self.modifier


class TempSpeedModifier(SpeedModifier):
    intervals = None  # type: TempSpeedModifierIntervals

    def __init__(self, intervals):
        self.intervals = TempSpeedModifierIntervals(intervals)

    def calculate(self, speed, temp):  # type: (float, float) -> float
        return self.intervals.get(temp).calculate(speed)


class TempSpeedModifierIntervals:
    list = []  # type: typing.List[TempSpeedModifierInterval]

    def __init__(self, intervals):
        def comp(a, b):  # type: (TempSpeedModifierInterval,TempSpeedModifierInterval) -> float
            return a.temp - b.temp

        self.list = [TempSpeedModifierInterval(**interval) for interval in intervals]
        self.list.sort(key=comp)

    def get(self, temp):  # type: (float) -> TempSpeedModifierInterval
        if not self.list:
            return TempSpeedModifierInterval()
        if temp < self.list[0].temp:
            return TempSpeedModifierInterval(modifier=self.list[0].modifier)
        if len(self.list) == 1:
            return self.list[0]
        if temp > self.list[-1].temp:
            return self.list[-1]

        ll = 0
        ul = len(self.list) - 1
        if ul == 0:
            return self.list[0]

        while True:
            i = ll + math.floor((ul - ll) / 2)
            if self.list[i].temp < temp < self.list[i + 1].temp:
                return self.list[i]
            if self.list[i].temp > temp:
                ul = i
            else:
                ll = i


class TempSpeedModifierInterval:
    temp = None  # type: float
    modifier = None  # type: float
    fix = None  # type: bool

    def __init__(
            self,
            temp=0,  # type: float
            modifier=0,  # type: float
            fix=False  # type: bool
    ):
        self.temp = temp
        self.modifier = modifier
        self.fix = fix

    def calculate(self, speed):  # type: (float) -> float
        if self.fix:
            return self.modifier
        return speed + self.modifier


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
