#!/usr/bin/python
## @package RAID5.common.utilities.config_util
# Module that defines many configuration file utilities
#

import uuid
import ConfigParser

from common.utilities import constants
from common.utilities import util

## function creates a block device configuration file in filename specified
## @param filename (string) filename of config_file
## @param index (int) block device numbering (for different disk and info
## files)
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

## function creates a frontend configuration file in filename specified
## @param filename (string) filename of config_file
def create_frontend_config(filename):
    with open(filename, 'w') as config_file:
        parser = ConfigParser.ConfigParser()
        common_config(parser)
        parser.write(config_file)

## function that writes a section of a configuration file
## @param filename (string) filename of config_file
## @param new_section (string) name of the new_section
## @param new_fields (dict) dict of new fields for the new section
def write_section_config(filename, new_section, new_fields):
    parser = ConfigParser.ConfigParser()
    parser.read(filename)

    # add content to the parser
    parser.add_section(new_section)
    for field, value in new_fields.items():
        parser.set(new_section, field, value)

    with open(filename, 'wb') as config_file:
        parser.write(config_file)

## function that writes a field of an existing section in a configuration file
## @param filename (string) filename of config_file
## @param section (string) name of the existing section
## @param fieldname (string) name of the new field name
## @param value (string) name of the new field value
def write_field_config(filename, section, fieldname, value):
    parser = ConfigParser.ConfigParser()
    parser.read(filename)
    parser.set(section, fieldname, value)
    with open(filename, 'wb') as config_file:
        parser.write(config_file)

## function adds common sections and field between Frontend and Block Device
## @param parser (ConfigParser) parser of an existing config_file
def common_config(parser):
    parser.add_section("MulticastGroup")
    parser.set("MulticastGroup", "address", "239.192.0.100")
    parser.set("MulticastGroup", "port", "5000")

    parser.add_section("Authentication")
    parser.set("Authentication", "common_user", "Roy")
    parser.set("Authentication", "common_password", "12345")

## function that parses a config_file
## @param config_file (string) filename of config_file
## @returns sections (dict) returns a dict of all the sections in the
## configuration file
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

## function creates a single dict section from parser
## @param parser (ConfigParser) parser of an existing config_file
## @param section (string) name of the existing section
## @returns dict1 (dict) returns dict with the config fields
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
