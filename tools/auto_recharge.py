# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

# Check battery level and recharge when below specified threshold

from builtins import *
from core.parameters import Params
from core.app_scenario import Scenario
import logging
import time
import subprocess

class Tool(Scenario):
    '''
    Pause run and recharge device when battery drops below [charge_threshold], then resume.

    Set charge_on_call and charge_off_call in the [global] section of the device profile
    to the full shell command that turns the charger on/off. If the command points to a
    .ps1 script it will be wrapped with powershell.exe automatically, so you can paste
    the invocation directly, e.g.:
      charge_on_call:  C:\pdu_controller\apc_pdu_controller.ps1 on 7 -PduIp 10.150.18.38 -Community hobl
      charge_off_call: C:\pdu_controller\apc_pdu_controller.ps1 off 7 -PduIp 10.150.18.38 -Community hobl
    '''
    module = __module__.split('.')[-1]
    # Set default parameters
    Params.setDefault(module, 'charge_threshold', '40')  # Percent battery level (40%)
    Params.setDefault(module, 'resume_threshold', '95')  # Percent battery level (95%)
    Params.setDefault('charge_on', 'charge_on_call', '')
    Params.setDefault('charge_off', 'charge_off_call', '')

    # Get parameters
    charge_threshold = Params.get(module, 'charge_threshold')
    resume_threshold = Params.get(module, 'resume_threshold')

    charge_on_call = Params.get('global', 'charge_on_call')
    charge_off_call = Params.get('global', 'charge_off_call')

    if charge_on_call == '' or charge_on_call is None:
        charge_on_call = Params.get('charge_on', 'charge_on_call')
    if charge_off_call == '' or charge_off_call is None:
        charge_off_call = Params.get('charge_off', 'charge_off_call')

    already_started = False

    def testBeginEarlyCallback(self, scenario):
        self.initCallback(scenario)
        self.already_started = True

    def initCallback(self, scenario):
        if self.already_started:
            return
        MAX_COUNT = 10
        count = 0

        batt_level = self.getBattLevel()
        logging.info("Battery level: " + batt_level)
        
        if int(batt_level) <= int(self.charge_threshold):
            logging.info("Charging...")
            # Start charging and wait until resume_threshold reached
            self.chargeOn()
        
            old_batt_level = -1
            # TODO: handle errors
            while True:
                try:
                    batt_level = self.getBattLevel()
                except:
                    time.sleep(300)
                    continue
                logging.info("Battery level: " + batt_level)
                if int(batt_level) >= int(self.resume_threshold):
                    logging.info("Charging complete")
                    # Disengage charging
                    self.chargeOff()
                    # TODO: handle errors
                    break
                else:
                    if batt_level == old_batt_level:
                        count += 1
                        logging.info("Seeing same battery level for " + str(count) + " times.")
                    else:
                        count = 0
                    if count == MAX_COUNT:
                        logging.info(f"Disengaging charger since seeing same battery level for {MAX_COUNT} times.")
                        self.chargeOff()
                        break
                    time.sleep(300) # sleep 5 minutes
                    old_batt_level = batt_level

    def testBeginCallback(self):
        pass

    def testEndCallback(self):
        pass

    def dataReadyCallback(self):
        pass

    def getBattLevel(self):
        if self.platform.lower() == "android":
            command = "adb "
            # if device_ip is not None:
            command = command + "-s " + str(self.dut_ip) + ":5555 "
            command = command + "shell \"dumpsys battery | grep 'level'|cut -f2 -d ':'\""
            p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell = True)
            out, err = p.communicate()
            actual_exit_code = p.returncode
            batt_level = str(out.decode('utf-8').rstrip())
        else:
            batt_level = self._call(["powershell.exe", "Add-Type -Assembly System.Windows.Forms; [Math]::round(([System.Windows.Forms.SystemInformation]::PowerStatus.BatteryLifePercent) * 100, 2)"])
        return batt_level

    def chargeOn(self):
        logging.info("Attempting to turn on charger...")
        if self.charge_on_call:
            self._host_call(self._wrap_ps1(self.charge_on_call))
            if Params.get('global', 'local_execution') == '1':
                self._host_call('utilities\\MsgPrompt.exe -WaitForAC')
        else:
            logging.warning("No charge_on_call specified.")
        logging.info("Charger on.")

    def chargeOff(self):
        logging.info("Attempting to turn off charger...")
        if self.charge_off_call:
            self._host_call(self._wrap_ps1(self.charge_off_call))
            if Params.get('global', 'local_execution') == '1':
                self._host_call('utilities\\MsgPrompt.exe -WaitForDC')
        else:
            logging.warning("No charge_off_call specified.")
        logging.info("Charger off.")

    def _wrap_ps1(self, call):
        '''If the call targets a .ps1 script, prepend powershell.exe so that
        cmd.exe (used by _host_call via shell=True) can execute it.
        Example input:  C:\\pdu_controller\\script.ps1 off 7 -PduIp 10.0.0.1
        Example output: powershell.exe -ExecutionPolicy Bypass -File "C:\\pdu_controller\\script.ps1" off 7 -PduIp 10.0.0.1
        '''
        stripped = call.strip().strip('"')
        first_token = stripped.split()[0] if stripped else ''
        if first_token.lower().endswith('.ps1'):
            # Split off the script path from its arguments
            rest = stripped[len(first_token):].lstrip()
            args_suffix = f' {rest}' if rest else ''
            return f'powershell.exe -ExecutionPolicy Bypass -File "{first_token}"{args_suffix}'
        return call
