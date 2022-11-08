#!/usr/bin/env python3
# coding: utf-8
import argparse
import json
import math
import os
import datetime
import sys
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

GPIO.setwarnings(False)


class Controller:
    pwm = None  # type: GPIO.PWM
    pin = None  # type: int

    @staticmethod
    def run():
        pass

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
        if speed < min_speed and speed != 0:
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
            instance.install()

        if instance.min is None:
            instance.calibrate_min_speed()

        menu = [
            {'name': 'Calibrate Start Speed', 'method': instance.calibrate_min_speed},
            {'name': 'Set Start Speed', 'method': instance.set_min_speed},
            {'name': 'Calibrate Frequency', 'method': instance.calibrate_frequency},
            {'name': 'Change Fan GPIO Pin', 'method': instance.set_pin},
            {'name': 'Save and Exit', 'method': Config.save_and_exit},
            {'name': 'Exit', 'method': Config.exit},
        ]

        print('What would you like to do?\n')
        for i in range(len(menu)):
            print('{i}. {name}'.format(i=i, name=menu[i]['name']))

        menu_index = input('\nMenu Index: ')
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
            Config.config.config_modified = False
        if read_modifier:
            Config.read('modifier')
            Config.config.modifier_modified = False

    @staticmethod
    def exit():
        ex = True
        if Config.config and (Config.config.config_modified or Config.config.modifier_modified):
            ex = input('Are you sure you want to quit? Your changes will not be saved! [y/n] ').lower() == 'y'
        if ex:
            sys.exit()

    @staticmethod
    def save_and_exit():
        Config.save(True)
        sys.exit()

    @staticmethod
    def save(info=False):
        if not Config.config:
            return
        if Config.config.config_modified:
            if info:
                # TODO: Check if the script is running
                print('\nYou need to restart {} for the changes to take effect!'.format(os.path.basename(__file__)))
            Config.write('config')
        if Config.config.modifier_modified:
            Config.write('modifier')

    @staticmethod
    def read(filename):
        for k, v in IO.read(Config.filename(filename)).items():
            setattr(Config.config, k, v)

    @staticmethod
    def write(filename):
        IO.write(Config.filename(filename), getattr(Config.config, '{}_data'.format(filename)))

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
    data = {}

    def __setattr__(self, key, value):
        if key in ['freq', 'min', 'pin']:
            self.data['config_modified'] = True
            self.config_data[key] = value
        elif key in ['periods']:
            if key in ['periods']:
                value = ModificationPeriods(value)
            self.data['modifier_modified'] = True
            self.modifier_data[key] = value
        else:
            self.data[key] = value

    def __getattr__(self, item):
        if item in self.config_data:
            return self.config_data[item]
        if item in self.modifier_data:
            return self.modifier_data[item]
        if item in self.data:
            return self.data[item]
        return None

    def install(self):
        self.set_pin()

        Controller.speed(100)

        works = input('Is the fan working properly? [y/n]: ').lower() == 'y'
        print()

        if not works:
            self.calibrate_frequency()

        # self.calibrate_min_speed()

    def set_pin(self):
        print()
        pin = input('Fan GPIO Pin: ')
        pins = list(range(2, 13 + 1)) + list(range(16, 27 + 1))
        if not pin.isnumeric() or int(pin) not in pins:
            print('\nInvalid GPIO Pin: {}! Valid pins: {}\n'.format(pin, ', '.join(pins)))
            return self.set_pin()

        print('\nThe set pin is {}\n'.format(pin))
        self.pin = int(pin)

    def calibrate_min_speed(self):
        def wait(msg='Waiting to stop... {}s'):
            w = 3
            for i in range(w + 1):
                print(msg.format(w - i), end='\r')
                time.sleep(1)

        print()
        Controller.speed(0)
        wait('Calibrate the fan start speed [%]... {}s')
        print()

        ll = 0
        ul = 100
        min_speed = None

        while True:
            speed = ll + math.floor((ul - ll) / 2)

            Controller.speed(speed, 0)
            is_spinning = input('Is the fan spinning ({}%)? [y/n]: '.format(speed)).lower() == 'y'

            if is_spinning:
                ul = speed
            else:
                ll = speed

            if ll == ul or ll == speed + 1 or ul == speed + 1:
                break

            if is_spinning:
                min_speed = speed
                Controller.speed(0)
                wait()

        print('\nTest 5 times...\n')

        is_spinning = True
        i = 0
        while i < 5:
            if is_spinning:
                Controller.speed(0)
                wait()
            else:
                min_speed += 1
                i = 0
                print('\nNew value: {}%\n'.format(min_speed))

            Controller.speed(min_speed)
            is_spinning = input('{}. Is the fan spinning? [y/n]: '.format(i + 1)).lower() == 'y'
            i += 1

        min_speed += 1
        print('\nThe start speed is {}% (with 1% correction)\n'.format(min_speed))
        self.min = min_speed

    def set_min_speed(self):
        speed = input('Start speed [%]: ').rstrip(' %')

        if not speed.isnumeric() or int(speed) < 1:
            print('\nInvalid Speed value: {}\n'.format(speed))
            return self.set_min_speed()

        speed = int(speed)
        Controller.speed(speed, 0)

        is_spinning = input('Is the fan spinning ({}%)? [y/n]: '.format(speed)).lower() == 'y'

        if not is_spinning:
            return self.set_min_speed()

        self.min = speed

    def calibrate_frequency(self):
        Controller.speed(100)
        print('\nChange the value until the fan working properly. When it fine, write done.\n')
        valid = False

        while True:
            freq = input('Frequency value [Hz]: ').rstrip(' HhZz')
            if freq.lower() == 'done':
                print('\nThe set frequency is {}Hz\n'.format(freq))
                break
            if not freq.isnumeric() or int(freq) < 1:
                print('\nInvalid Frequency value: {}\n'.format(freq))
                valid = False
                continue
            valid = True
            Controller.freq(int(freq))

        if valid:
            print('\nThe set Frequency is {}\n'.format(freq))
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

    config_modified = False
    modifier_modified = False


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
            if self.list[i].temp <= temp < self.list[i + 1].temp:
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
        filename = IO.filename(filename)
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(dictionary, f)

    @staticmethod
    def filename(filename):  # type: (str) -> str
        return '{root}/{file}'.format(root=IO.ROOT, file=filename)


def run():
    try:
        Controller.run()
    except KeyboardInterrupt:
        GPIO.cleanup()
        sys.exit()
    except (RuntimeError, Exception) as e:
        GPIO.cleanup()
        time.sleep(1)
        run()


def config():
    try:
        Config.menu()
    except KeyboardInterrupt:
        Config.exit()
        Config.menu()


def from_args():
    parser = argparse.ArgumentParser(description='Fan Controller')
    sub_parser = parser.add_subparsers(dest='command')

    config_parser = sub_parser.add_parser('config', help='Fan Controller Configuration')

    args = parser.parse_args()

    if args.command == 'config':
        config()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        run()
    else:
        from_args()
