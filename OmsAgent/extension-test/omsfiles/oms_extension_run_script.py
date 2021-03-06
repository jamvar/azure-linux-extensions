import os
import os.path
import platform
import subprocess
import re
import sys
import time

if "check_output" not in dir( subprocess ): # duck punch it in!
        def check_output(*popenargs, **kwargs):
            r"""Run command with arguments and return its output as a byte string.
            Backported from Python 2.7 as it's implemented as pure python on stdlib.
            >>> check_output(['/usr/bin/python', '--version'])
            Python 2.6.2
            """
            process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
            output, unused_err = process.communicate()
            retcode = process.poll()
            if retcode:
                cmd = kwargs.get("args")
                if cmd is None:
                    cmd = popenargs[0]
                error = subprocess.CalledProcessError(retcode, cmd)
                error.logput = output
                raise error
            return output

        subprocess.check_output = check_output

operation = None

outFile = '/tmp/omsresults.log'
openFile = open(outFile, 'w+')

def main():
    # Determine the operation being executed
    vm_supported, vm_dist, vm_ver = is_vm_supported_for_extension()
    linux_detect_installer()
    
    global operation
    if len(sys.argv) == 2:
        option = sys.argv[1]
        if re.match('^([-/]*)(preinstall)', option):
            install_additional_packages()
        elif re.match('^([-/]*)(postinstall)', option):
            detect_workspace_id()
            config_start_oms_services()
            restart_services()
            time.sleep(30)
            inject_logs()
            result_commands()
            service_control_commands()
            write_html()
            dist_status()
        elif re.match('^([-/]*)(status)', option):
            result_commands()
            service_control_commands()
            write_html()
            dist_status()
        elif re.match('^([-/]*)(copyextlogs)', option):
            copy_extension_log()
    else:
        print "No operation specified. run with 'preinstall' or 'postinstall' or 'status' or 'copyextlogs'"

def is_vm_supported_for_extension():

    global vm_supported, vm_dist, vm_ver
    supported_dists = {'redhat' : ['6', '7'], # CentOS
                       'centos' : ['6', '7'], # CentOS
                       'red hat' : ['6', '7'], # Oracle, RHEL
                       'oracle' : ['6', '7'], # Oracle
                       'debian' : ['8', '9'], # Debian
                       'ubuntu' : ['14.04', '16.04', '18.04'], # Ubuntu
                       'suse' : ['12'] #SLES
    }

    try:
        vm_dist, vm_ver, vm_id = platform.linux_distribution()
    except AttributeError:
        vm_dist, vm_ver, vm_id = platform.dist()

    vm_supported = False

    # Find this VM distribution in the supported list
    for supported_dist in supported_dists.keys():
        if not vm_dist.lower().startswith(supported_dist):
            continue

        # Check if this VM distribution version is supported
        vm_ver_split = vm_ver.split('.')
        for supported_ver in supported_dists[supported_dist]:
            supported_ver_split = supported_ver.split('.')

            vm_ver_match = True
            for idx, supported_ver_num in enumerate(supported_ver_split):
                try:
                    supported_ver_num = int(supported_ver_num)
                    vm_ver_num = int(vm_ver_split[idx])
                except IndexError:
                    vm_ver_match = False
                    break
                if vm_ver_num is not supported_ver_num:
                    vm_ver_match = False
                    break
            if vm_ver_match:
                vm_supported = True
                break

        if vm_supported:
            break

    return vm_supported, vm_dist, vm_ver

def replace_items(infile,old_word,new_word):
    if not os.path.isfile(infile):
        print "Error on replace_word, not a regular file: "+infile
        sys.exit(1)

    f1=open(infile,'r').read()
    f2=open(infile,'w')
    m=f1.replace(old_word,new_word)
    f2.write(m)

def detect_workspace_id():
    """Detect the workspace id where the agent is onboarded."""
    global workspace_id
    x = subprocess.check_output('/opt/microsoft/omsagent/bin/omsadmin.sh -l', shell=True)
    try:
        workspace_id = re.search('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', x).group(0)
    except AttributeError:
        workspace_id = None

def linux_detect_installer():
    global INSTALLER
    INSTALLER=None
    if vm_supported and (vm_dist.startswith('Ubuntu') or vm_dist.startswith('debian')):
        INSTALLER='APT'
    elif vm_supported and (vm_dist.startswith('CentOS') or vm_dist.startswith('Oracle') or vm_dist.startswith('Red Hat')):
        INSTALLER='YUM'
    elif vm_supported  and vm_dist.startswith('SUSE Linux'):
        INSTALLER='ZYPPER'

def install_additional_packages():
    #Add additional packages command here
    if INSTALLER == 'APT':
        os.system('apt-get -y install wget apache2 git dos2unix \
                && service apache2 start')
    elif INSTALLER == 'YUM':
        os.system('yum install -y wget httpd git dos2unix \
                && service httpd start')
    elif INSTALLER == 'ZYPPER':
        os.system('zypper install -y wget httpd git dos2unix\
                && service apache2 start')

def enable_dsc():
    os.system('/opt/microsoft/omsconfig/Scripts/OMS_MetaConfigHelper.py --enable')

def disable_dsc():
    os.system('/opt/microsoft/omsconfig/Scripts/OMS_MetaConfigHelper.py --disable')
    Pending_mof = '/etc/opt/omi/conf/omsconfig/configuration/Pending.mof'
    Current_mof = '/etc/opt/omi/conf/omsconfig/configuration/Pending.mof'
    if os.path.isfile(Pending_mof) or os.path.isfile(Current_mof):
        os.remove(Pending_mof)
        os.remove(Current_mof)

def copy_config_files():
    os.system('dos2unix /tmp/perf.conf \
            && dos2unix /tmp/rsyslog-oms.conf \
            && dos2unix /tmp/apache_access.log \
            && dos2unix /tmp/custom.log \
            && dos2unix /tmp/error.log \
            && dos2unix /tmp/mysql-slow.log \
            && dos2unix /tmp/mysql.log \
            && cat /tmp/perf.conf >> /etc/opt/microsoft/omsagent/{0}/conf/omsagent.conf \
            && cp /tmp/rsyslog-oms.conf /etc/opt/omi/conf/omsconfig/rsyslog-oms.conf \
            && cp /tmp/rsyslog-oms.conf /etc/rsyslog.d/95-omsagent.conf \
            && chown omsagent:omiusers /etc/rsyslog.d/95-omsagent.conf \
            && chmod 644 /etc/rsyslog.d/95-omsagent.conf \
            && cp /tmp/customlog.conf /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/customlog.conf \
            && chown omsagent:omiusers /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/customlog.conf \
            && cp /etc/opt/microsoft/omsagent/sysconf/omsagent.d/apache_logs.conf /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/apache_logs.conf \
            && chown omsagent:omiusers /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/apache_logs.conf \
            && cp /etc/opt/microsoft/omsagent/sysconf/omsagent.d/mysql_logs.conf /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/mysql_logs.conf \
            && chown omsagent:omiusers /etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/mysql_logs.conf'.format(workspace_id))
    replace_items('/etc/opt/microsoft/omsagent/{0}/conf/omsagent.conf'.format(workspace_id), '<workspace-id>', workspace_id)
    replace_items('/etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/customlog.conf'.format(workspace_id), '<workspace-id>', workspace_id)

def apache_mysql_conf():
    """Configure Apache and MySQL, set up empty log files, and add permissions."""
    apache_conf_file = '/etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/apache_logs.conf'.format(workspace_id)
    mysql_conf_file = '/etc/opt/microsoft/omsagent/{0}/conf/omsagent.d/mysql_logs.conf'.format(workspace_id)
    apache_access_conf_path_string = '/usr/local/apache2/logs/access_log /var/log/apache2/access.log /var/log/httpd/access_log /var/log/apache2/access_log'
    apache_error_conf_path_string = '/usr/local/apache2/logs/error_log /var/log/apache2/error.log /var/log/httpd/error_log /var/log/apache2/error_log'
    os.system('chown omsagent:omiusers {0}'.format(apache_conf_file))
    os.system('chown omsagent:omiusers {0}'.format(mysql_conf_file))

    os.system('mkdir -p /var/log/mysql \
            && touch /var/log/mysql/mysql.log /var/log/mysql/error.log /var/log/mysql/mysql-slow.log \
            && touch /var/log/custom.log \
            && chmod +r /var/log/mysql/* \
            && chmod +rx /var/log/mysql \
            && chmod +r /var/log/custom.log')

    if INSTALLER == 'APT':
        replace_items(apache_conf_file, apache_access_conf_path_string, '/var/log/apache2/access.log')
        replace_items(apache_conf_file, apache_error_conf_path_string, '/var/log/apache2/error.log')
        os.system('mkdir -p /var/log/apache2 \
                && touch /var/log/apache2/access.log /var/log/apache2/error.log \
                && chmod +r /var/log/apache2/* \
                && chmod +rx /var/log/apache2')
    elif INSTALLER == 'YUM':
        replace_items(apache_conf_file, apache_access_conf_path_string, '/var/log/httpd/access_log')
        replace_items(apache_conf_file, apache_error_conf_path_string, '/var/log/httpd/error_log')
        os.system('mkdir -p /var/log/httpd \
                && touch /var/log/httpd/access_log /var/log/httpd/error_log \
                && chmod +r /var/log/httpd/* \
                && chmod +rx /var/log/httpd')
    elif INSTALLER == 'ZYPPER':
        replace_items(apache_conf_file, apache_access_conf_path_string, '/var/log/apache2/access_log')
        replace_items(apache_conf_file, apache_error_conf_path_string, '/var/log/apache2/error_log')
        os.system('mkdir -p /var/log/apache2 \
                && touch /var/log/apache2/access_log /var/log/apache2/error_log \
                && chmod +r /var/log/apache2/* \
                && chmod +rx /var/log/apache2')

def inject_logs():
    """Inject logs (after) agent is running in order to simulate real Apache/MySQL/Custom logs output."""
    if INSTALLER == 'APT':
        os.system('cp /tmp/apache_access.log /var/log/apache2/access.log \
                && chown root:root /var/log/apache2/access.log \
                && chmod 644 /var/log/apache2/access.log \
                && dos2unix /var/log/apache2/access.log')
    elif INSTALLER == 'YUM':
        os.system('cp /tmp/apache_access.log /var/log/httpd/access_log \
                && chown root:root /var/log/httpd/access_log \
                && chmod 644 /var/log/httpd/access_log \
                && dos2unix /var/log/httpd/access_log')
    elif INSTALLER == 'ZYPPER':
        os.system('cp /tmp/apache_access.log /var/log/apache2/access_log \
                && chown root:root /var/log/apache2/access_log \
                && chmod 644 /var/log/apache2/access_log \
                && dos2unix /var/log/apache2/access_log')

    os.system('cp /tmp/mysql.log /var/log/mysql/mysql.log \
            && cp /tmp/error.log /var/log/mysql/error.log \
            && cp /tmp/mysql-slow.log /var/log/mysql/mysql-slow.log \
            && cp /tmp/custom.log /var/log/custom.log')

def config_start_oms_services():
    """Orchestrate overall configuration prior to agent start."""
    os.system('/opt/omi/bin/omiserver -d')
    disable_dsc()
    copy_config_files()
    apache_mysql_conf()

def restart_services():
    time.sleep(10)
    os.system('service rsyslog restart \
                && /opt/omi/bin/service_control restart \
                && /opt/microsoft/omsagent/bin/service_control restart')


def append_file(filename, destFile):
    f = open(filename, 'r')
    destFile.write(f.read())
    f.close()

def exec_command(cmd):
    """Run the provided command, check, and return its output."""
    try:
        out = subprocess.check_output(cmd, shell=True)
        return out
    except subprocess.CalledProcessError as e:
        print(e.returncode)
        return e.returncode

def write_log_output(openFile, out):
    """Save command output to the log file."""
    if(type(out) != str):
        out = str(out)
    openFile.write(out + '\n')
    openFile.write('-' * 80)
    openFile.write('\n')

def write_log_command(openFile, cmd):
    """Print command and save command to log file."""
    print(cmd)
    openFile.write(cmd + '\n')
    openFile.write('=' * 40)
    openFile.write('\n')

def check_pkg_status(pkg):
    """Check pkg install status and return output and derived status."""
    if INSTALLER == 'APT':
        cmd = 'dpkg -s {0}'.format(pkg)
        output = exec_command(cmd)
        if (os.system('{0} | grep deinstall > /dev/null 2>&1'.format(cmd)) == 0 or
                os.system('dpkg -s omsagent > /dev/null 2>&1') != 0):
            status = 'Not Installed'
        else:
            status = 'Install Ok'
    elif INSTALLER == 'YUM' or INSTALLER == 'ZYPPER':
        cmd = 'rpm -qi {0}'.format(pkg)
        output = exec_command(cmd)
        if os.system('{0} > /dev/null 2>&1'.format(cmd)) == 0:
            status = 'Install Ok'
        else:
            status = 'Not Installed'

    write_log_command(openFile, cmd)
    write_log_output(openFile, output)
    return (output, status)

def result_commands():
    global waagentOut, onboardStatus, omiRunStatus, psefomsagent, omsagentRestart, omiRestart
    global omiInstallOut, omsagentInstallOut, omsconfigInstallOut, scxInstallOut, omiInstallStatus, omsagentInstallStatus, omsconfigInstallStatus, scxInstallStatus
    cmd='waagent --version'
    waagentOut = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, waagentOut)
    cmd = '/opt/microsoft/omsagent/bin/omsadmin.sh -l'
    onboardStatus = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, onboardStatus)
    cmd = 'scxadmin -status'
    omiRunStatus = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, omiRunStatus)

    omiInstallOut, omiInstallStatus = check_pkg_status('omi')
    omsagentInstallOut, omsagentInstallStatus = check_pkg_status('omsagent')
    omsconfigInstallOut, omsconfigInstallStatus = check_pkg_status('omsconfig')
    scxInstallOut, scxInstallStatus = check_pkg_status('scx')

    # OMS agent process check
    cmd = 'ps -ef | egrep "omsagent|omi"'
    psefomsagent = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, psefomsagent)

    time.sleep(10)
    # OMS agent restart
    cmd = '/opt/microsoft/omsagent/bin/service_control restart'
    omsagentRestart = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, omsagentRestart)

    # OMI agent restart
    cmd = '/opt/omi/bin/service_control restart'
    omiRestart = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, omiRestart)

def service_control_commands():
    """Determine and store results of various service commands."""
    global serviceStop, serviceDisable, serviceEnable, serviceStart

    # OMS stop (shutdown the agent)
    cmd = '/opt/microsoft/omsagent/bin/service_control stop'
    serviceStop = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, serviceStop)

    # OMS disable (disable agent from starting upon system start)
    cmd = '/opt/microsoft/omsagent/bin/service_control disable'
    serviceDisable = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, serviceDisable)

    # OMS enable (enable agent to start upon system start)
    cmd = '/opt/microsoft/omsagent/bin/service_control enable'
    serviceEnable = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, serviceEnable)

    # OMS start (start the agent)
    cmd = '/opt/microsoft/omsagent/bin/service_control start'
    serviceStart = exec_command(cmd)
    write_log_command(openFile, cmd)
    write_log_output(openFile, serviceStart)

def write_html():
    os.system('rm /tmp/omsresults.html')
    htmlFile = '/tmp/omsresults.html'
    f = open(htmlFile, 'w+')
    message="""
<div class="text" style="white-space: pre-wrap" >

<table>
  <caption><h4>OMS Install Results</h4><caption>
  <tr>
    <th>Package</th>
    <th>Status</th>
    <th>Output</th>
  </tr>
  <tr>
    <td>OMI</td>
    <td>{0}</td>
    <td>{1}</td>
  </tr>
  <tr>
    <td>OMSAgent</td>
    <td>{2}</td>
    <td>{3}</td>
  </tr>
  <tr>
    <td>OMSConfig</td>
    <td>{4}</td>
    <td>{5}</td>
  </tr>
  <tr>
    <td>SCX</td>
    <td>{6}</td>
    <td>{7}</td>
  </tr>
</table>

<table>
  <caption><h4>OMS Command Outputs</h4><caption>
  <tr>
    <th>Command</th>
    <th>Output</th>
  </tr>
  <tr>
    <td>waagent --version</td>
    <td>{8}</td>
  </tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/omsadmin.sh -l</td>
    <td>{9}</td>
  </tr>
  <tr>
    <td>scxadmin -status</td>
    <td>{10}</td>
  </tr>
  <tr>
    <td>ps -ef | egrep "omsagent|omi"</td>
    <td>{11}</td>
  </tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/service_control restart</td>
    <td>{12}</td>
  <tr>
  <tr>
    <td>/opt/omi/bin/service_control restart</td>
    <td>{13}</td>
  <tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/service_control stop</td>
    <td>{14}</td>
  <tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/service_control disable</td>
    <td>{15}</td>
  <tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/service_control enable</td>
    <td>{16}</td>
  <tr>
  <tr>
    <td>/opt/microsoft/omsagent/bin/service_control stop</td>
    <td>{17}</td>
  <tr>
</table>
</div>
""".format(omiInstallStatus, omiInstallOut, omsagentInstallStatus, omsagentInstallOut, omsconfigInstallStatus, omsconfigInstallOut, scxInstallStatus, scxInstallOut, waagentOut, onboardStatus, omiRunStatus, psefomsagent, omsagentRestart, omiRestart, serviceStop, serviceDisable, serviceEnable, serviceStart)

    f.write(message)
    f.close()

def dist_status():
    f = open('/tmp/omsresults.status', 'w+')
    if os.system('/opt/microsoft/omsagent/bin/omsadmin.sh -l') == 0:
        detect_workspace_id()
        x_out = subprocess.check_output('/opt/microsoft/omsagent/bin/omsadmin.sh -l', shell=True)
        if x_out.rstrip() == "No Workspace":
            status_message = "Onboarding Failed"
        elif re.search('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', x_out).group(0) == workspace_id:
            status_message = "Agent Found"
    else:
        status_message = "Agent Not Found"
    f.write(status_message)
    f.close()

def sorted_dir(folder):
    def getmtime(name):
        path = os.path.join(folder, name)
        return os.path.getmtime(path)
    
    return sorted(os.listdir(folder), key=getmtime, reverse=True)

def copy_extension_log():
    extlogfile = ""
    split_name = vm_dist.split(' ')
    split_ver = vm_ver.split('.')
    if vm_dist.startswith('Red Hat'):
        extlogfile = '/tmp/{0}-extension.log'.format((split_name[0]+split_name[1]).lower()+split_ver[0])
    else:
        extlogfile = '/tmp/{0}-extension.log'.format(split_name[0].lower()+split_ver[0])

    extlogfileOpen = open(extlogfile, 'a+')
    oms_azure_ext_dir = '/var/log/azure/Microsoft.EnterpriseCloud.Monitoring.OmsAgentForLinux/'
    ext_vers = sorted_dir(oms_azure_ext_dir)
    write_log_command(extlogfileOpen, 'Extension Install Logs:')
    if ext_vers[0].startswith('extension'):
        append_file(oms_azure_ext_dir + ext_vers[0], extlogfileOpen)
    else:
        append_file(oms_azure_ext_dir + ext_vers[0] + '/extension.log', extlogfileOpen)
    extlogfileOpen.close()
    

if __name__ == '__main__' :
    main()
