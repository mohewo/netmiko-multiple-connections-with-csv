import csv
import datetime as dt
from logging import DEBUG
from logging import Formatter, getLogger, StreamHandler, FileHandler
import os
from typing import Callable, Dict, List

import netmiko
from netmiko.ssh_autodetect import SSHDetect
from netmiko.ssh_dispatcher import ConnectHandler
from netmiko import utilities as netutil

import ping3 as ping

ping.EXCEPTIONS = True


class CSVOperator:

    def read_hostlist(self, csv_file: str = "hostlist.csv") -> List[Dict[str, str]]:
        try:
            with open(csv_file, 'r') as f:
                hostdict = csv.DictReader(f)
                hostlist = list(hostdict)
                return hostlist

        except IOError:
            print(f'I/O error: {csv_file}\n')

    def read_commandlist(self, csv_file: str = "commandlist.csv") -> List[List[str]]:
        try:
            with open(csv_file, 'r') as f:
                csv_reader = csv.reader(f)
                commandlist = list(csv_reader)
                del commandlist[0]
                return commandlist

        except IOError:
            print(f'I/O error: {csv_file}\n')


class NetmikoOperator:

    def __init__(self, host: Dict, commands: List, logdir: str) -> None:
        self.make_timeinfo()

        self.host = host
        self.hostname = host["host"]
        self.username = host["username"]
        self.password = host["password"]
        self.secret = host["secret"]
        self.commands = commands
        self.res = {}

        self.logdir = logdir
        file_prefix = f"{self.logdir}/{self.hostname}-{self.timeinfo}-JST"
        self.loggingfile = f"{file_prefix}-logging.log"
        self.outputfile = f"{file_prefix}.log"
        self.setup_logger()

    def make_timeinfo(self) -> Callable:
        self.timeinfo = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d-%H%M%S')

    def setup_logger(self) -> Callable:
        self.logger = getLogger(__name__)
        self.logger.setLevel(DEBUG)

        log_formatter = Formatter(
            '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
            '%Y-%m-%d %H:%M:%S')

        std_err = StreamHandler()
        std_err.setFormatter(log_formatter)

        fs_err = FileHandler(self.loggingfile)
        fs_err.setFormatter(log_formatter)

        self.logger.addHandler(std_err)
        self.logger.addHandler(fs_err)
        self.logger.propagate = False

    def connect_autodetect(self) -> Callable:
        remote_device = {'device_type': 'autodetect',
                         'host': self.hostname,
                         'username': self.username,
                         'password': self.password,
                         'secret': self.secret,
                         'session_log': self.outputfile
                         }
        remote_device['device_type'] = SSHDetect(**remote_device).autodetect()
        self.connection = ConnectHandler(**remote_device)

    def rename_logfile(self, key: str, loginfo: str) -> None:
        loginfo_renamed = loginfo.rstrip('.log') + f'-{key}.log'
        os.rename(loginfo, loginfo_renamed)

    def ping_check(self) -> None:
        try:
            ping.ping(self.host, timeout=0.5)

        except ping.errors.Timeout:
            error_msg = 'PingTimeout'
            self.logger.error(f'{error_msg}: {self.host}')

        except ping.errors.TimeToLiveExpired:
            error_msg = 'PingTTLExpired'
            self.logger.error(f'{error_msg}: {self.host}')

        except ping.errors.PingError:
            error_msg = 'PingUnreachable'
            self.logger.error(f'{error_msg}: {self.host}')

        except PermissionError:
            error_msg = 'PermissionError; OS requires root permission to send ICMP packets'
            self.logger.error(f'{error_msg}')

        except Exception as e:
            self.logger.error(f'Error: {self.host}')
            self.logger.debug(e)

        else:
            success_msg = 'PingSuccess'
            self.logger.info(f'{success_msg}: {self.host}')

    def wrapper_except_proccess(self, host: str, error_msg: str, loginfo: str) -> None:
        self.ping_check(host)
        self.logger.error(f'{error_msg}: {host}\n')
        self.rename_logfile(error_msg, loginfo)

    def single_send_command(self, command) -> str:
        self.connection.enable()
        print(f'{"="*30} {command} @{self.host} {"="*30}')
        output = self.connection.send_command(command, strip_prompt=False, strip_command=False) + '\n'
        self.res[command] = output
        print(output)
        print(f'{"="*80}\n')
        return output

    def multi_send_command(self) -> str:
        output = ""
        for command in self.commands:
            output += self.single_send_command(command)
        return output

    def exec_command(self):
        try:
            self.connect_autodetect()
            output = self.multi_send_command()

        except netmiko.NetMikoAuthenticationException:
            error_msg = 'SSHAuthenticationError'
            self.wrapper_except_proccess(self.host, error_msg, self.outputfile)

        except netmiko.NetMikoTimeoutException:
            error_msg = 'SSHTimeoutError'
            self.wrapper_except_proccess(self.host, error_msg, self.outputfile)

        except netmiko.ReadTimeout:
            error_msg = 'ReadTimeout or CommandMismatch'
            self.wrapper_except_proccess(self.host, error_msg, self.outputfile)

        except Exception as e:
            error_msg = 'Error'
            self.wrapper_except_proccess(self.host, error_msg, self.outputfile)
            self.logger.error(e)

        else:
            success_msg = 'SuccessfullyDone'
            self.logger.info(f'{success_msg}: {self.host}\n')
            return output

    def close(self):
        self.connection.disconnect()


def multi_connections(hlists, clist) -> None:
    timeinfo = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y%m%d-%H%M%S')
    logdir = f'log-{timeinfo}'
    netutil.ensure_dir_exists(logdir)

    session = {}

    for hinfo in hlists:
        session[hinfo["host"]] = NetmikoOperator(hinfo, clist, logdir)
        session[hinfo["host"]].exec_command()
        session[hinfo["host"]].close()


def main():
    csv_ope = CSVOperator()
    hlist = csv_ope.read_hostlist()
    clist = csv_ope.read_commandlist()

    multi_connections(hlist, clist)


if __name__ == '__main__':
    main()
