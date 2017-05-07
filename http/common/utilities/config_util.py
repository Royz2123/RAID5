# -*- coding: utf-8 -*-
import uuid
import ConfigParser

from http.common.utilities import constants

#creates a config file in filename specified, same for both frontend_server
# and bds_server for now
def create_bds_config(filename, index):
    cfgfile = open(filename,'w')
    parser = ConfigParser.ConfigParser()
    common_config(parser)
    parser.set("Server", "disk_info_name", "%s%s" % (
        constants.DISK_INFO_NAME,
        index
    ))
    parser.set("Server", "disk_name", "%s%s" % (
        constants.DISK_NAME,
        index
    ))
    parser.write(cfgfile)

def create_frontend_config(filename):
    cfgfile = open(filename,'w')
    parser = ConfigParser.ConfigParser()
    common_config(parser)
    parser.write(cfgfile)

def common_config(parser):
    parser.add_section("MulticastGroup")
    parser.set("MulticastGroup", "Address", "239.192.0.100")
    parser.set("MulticastGroup", "Port", "5000")

    parser.add_section("Authentication")
    parser.set("Authentication", "CommonUser", "Roy")
    parser.set("Authentication", "CommonPassword", "12345")
    parser.set("Authentication", "LongPassword", "")

    parser.add_section("Server")
    parser.set("Server", "UUID", str(uuid.uuid4()))


def parse_config(config_file):
    #Config-file handling
    Config = ConfigParser.ConfigParser()
    Config.read(config_file)

    #could add checks for validity of Config file

    #extract data from configfile
    sections = {}
    for section in Config.sections():
        sections[section] = create_dict_section(
            Config,
            section
        )
    print sections
    return sections

def create_dict_section(parser, section):
    dict1 = {}
    options = parser.options(section)
    for option in options:
        try:
            dict1[option] = parser.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1

# vim: expandtab tabstop=4 shiftwidth=4
