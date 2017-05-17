# -*- coding: utf-8 -*-
import uuid
import ConfigParser

from common.utilities import constants
from common.utilities import util

# creates a config file in filename specified, same for both frontend
# and block_device for now


def create_bds_config(filename, index):
    with open(filename, 'w') as config_file:
        parser = ConfigParser.ConfigParser()
        common_config(parser)
        parser.add_section("Server")
        parser.set("Server", "volume_UUID", "")
        parser.set("Server", "disk_UUID", util.generate_uuid())
        parser.set("Server", "disk_info_name", "%s%s" % (
            constants.DISK_INFO_NAME,
            index
        ))
        parser.set("Server", "disk_name", "%s%s" % (
            constants.DISK_NAME,
            index
        ))
        parser.write(config_file)


def create_frontend_config(filename):
    with open(filename, 'w') as config_file:
        parser = ConfigParser.ConfigParser()
        common_config(parser)
        parser.write(config_file)


def write_section_config(filename, new_section, new_fields):
    parser = ConfigParser.ConfigParser()
    parser.read(filename)

    # add content to the parser
    parser.add_section(new_section)
    for field, value in new_fields.items():
        parser.set(new_section, field, value)

    with open(filename, 'wb') as config_file:
        parser.write(config_file)


def write_field_config(filename, section, fieldname, value):
    parser = ConfigParser.ConfigParser()
    parser.read(filename)
    parser.set(section, fieldname, value)
    with open(filename, 'wb') as config_file:
        parser.write(config_file)


def common_config(parser):
    parser.add_section("MulticastGroup")
    parser.set("MulticastGroup", "address", "239.192.0.100")
    parser.set("MulticastGroup", "port", "5000")

    parser.add_section("Authentication")
    parser.set("Authentication", "common_user", "Roy")
    parser.set("Authentication", "common_password", "12345")


def parse_config(config_file):
    # Config-file handling
    Config = ConfigParser.ConfigParser()
    Config.read(config_file)

    # extract data from configfile
    sections = {}
    for section in Config.sections():
        sections[section] = create_dict_section(
            Config,
            section
        )
    return sections


def create_dict_section(parser, section):
    dict1 = {}
    options = parser.options(section)
    for option in options:
        try:
            dict1[option] = parser.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except BaseException:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1

# vim: expandtab tabstop=4 shiftwidth=4
