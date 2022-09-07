import csv
import datetime as dt
from logging import DEBUG
from logging import Formatter
from logging import getLogger
from logging import StreamHandler
import os
from typing import Callable
from typing import Dict
from typing import List

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

    def __init__(self) -> None:
        self.logger = self.setup_logger()

    def setup_logger(self) -> Callable:
        logger = getLogger(__name__)
        logger.setLevel(DEBUG)

        sh = StreamHandler()
        sh.setLevel(DEBUG)
        sh_formatter = Formatter(
            '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
            '%Y-%m-%d %H:%M:%S')
        sh.setFormatter(sh_formatter)

        logger.addHandler(sh)
        logger.propagate = False
        return logger

    def connect_autodetect(self, hostinfo: Dict[str, str], loginfo: str) -> Callable:
        remote_device = {'device_type': 'autodetect',
                         'host': hostinfo.get("host"),
                         'username': hostinfo.get("username"),
                         'password': hostinfo.get("password"),
                         'secret': hostinfo.get("secret"),
                         'session_log': loginfo}
        detector = SSHDetect(**remote_device)
        remote_device['device_type'] = detector.autodetect()
        connection = ConnectHandler(**remote_device)
        return connection

    def make_logdir(self, timeinfo: str) -> str:
        logdir = f'log-{timeinfo}'
        netutil.ensure_dir_exists(logdir)
        return logdir

    def make_loginfo(self, timeinfo: str, **hinfo) -> str:
        dir = self.make_logdir(timeinfo)
        loginfo = f'{dir}/{hinfo.get("host")}-{timeinfo}-JST.log'
        return loginfo

    def rename_logfile(self, key: str, loginfo: str) -> None:
        loginfo_renamed = loginfo.rstrip('.log') + f'-{key}.log'
        os.rename(loginfo, loginfo_renamed)

    def ping_check(self, host: str) -> None:
        try:
            ping.ping(host, timeout=0.5)

        except ping.errors.Timeout:
            error_msg = 'PingTimeout'
            self.logger.error(f'{error_msg}: {host}')

        except ping.errors.TimeToLiveExpired:
            error_msg = 'PingTTLExpired'
            self.logger.error(f'{error_msg}: {host}')

        except ping.errors.PingError:
            error_msg = 'PingUnreachable'
            self.logger.error(f'{error_msg}: {host}')

        except PermissionError:
            error_msg = 'PermissionError; OS requires root permission to send ICMP packets'
            self.logger.error(f'{error_msg}')

        except Exception as e:
            self.logger.error(f'Error: {host}')
            self.logger.debug(e)

        else:
            success_msg = 'PingSuccess'
            self.logger.info(f'{success_msg}: {host}')

    def wrapper_except_proccess(self, host: str, error_msg: str, loginfo: str) -> None:
        self.ping_check(host)
        self.logger.error(f'{error_msg}: {host}\n')
        self.rename_logfile(error_msg, loginfo)

    def multi_send_command(self, conn: Callable, commandlist: List[List[str]]) -> str:
        conn.enable()
        for command in commandlist:
            print(f'{"="*30} {command[0]} @{conn.host} {"="*30}')
            output = ''
            output += conn.send_command(command[0], strip_prompt=False, strip_command=False) + '\n'
            print(output)
            print(f'{"="*80}\n')
        return output

    def multi_connections(self, hostlist: List[Dict[str, str]], commandlist: List[List[str]]) -> None:
        dt_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
        dt_now = dt_now.strftime('%Y%m%d-%H%M%S')

        for hinfo in hostlist:
            loginfo = self.make_loginfo(dt_now, **hinfo)
            host = hinfo.get("host")

            try:
                conn = self.connect_autodetect(hinfo, loginfo)
                self.multi_send_command(conn, commandlist)
                conn.disconnect()

            except netmiko.NetMikoAuthenticationException:
                error_msg = 'SSHAuthenticationError'
                self.wrapper_except_proccess(host, error_msg, loginfo)

            except netmiko.NetMikoTimeoutException:
                error_msg = 'SSHTimeoutError'
                self.wrapper_except_proccess(host, error_msg, loginfo)

            except netmiko.ReadTimeout:
                error_msg = 'ReadTimeout or CommandMismatch'
                self.wrapper_except_proccess(host, error_msg, loginfo)

            except Exception as e:
                error_msg = 'Error'
                self.wrapper_except_proccess(host, error_msg, loginfo)
                self.logger.error(e)

            else:
                success_msg = 'SuccessfullyDone'
                self.logger.info(f'{success_msg}: {host}\n')


def main():
    csv_ope = CSVOperator()
    hlist = csv_ope.read_hostlist()
    clist = csv_ope.read_commandlist()

    netmiko_ope = NetmikoOperator()
    netmiko_ope.multi_connections(hlist, clist)


if __name__ == '__main__':
    main()
